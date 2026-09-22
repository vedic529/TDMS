"""One student's own timetable, derived on every call.

Three subsystems already hold every piece of this and have never been joined:

* **What the student studies** — `rolling_timetable_weeks`, reached through the
  student's `student_groups.rolling_intake_label`.
* **When and where it is taught** — `allocation_delivery` / `allocation_session`,
  reached through `allocation_delivery_intake.intake_label`, the *same string*.
* **Which campus is theirs** — `students.course_offering_id`, because an intake
  label is not campus-specific and the same label runs at several campuses.

Two rules shape the whole module:

**The rolling timetable drives the list.** Allocations are joined *onto* it, never
the other way round. Driving from the allocation side would hide any unit whose
delivery never matched an intake, and the student would see a short timetable
with nothing to say anything was missing.

**Nothing is cached.** The endpoint reads the database when it is called, so a
resolved suggestion or an edited session shows up the next time the panel opens.

Exactly three queries, and one when the student has no intake at all.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.models.allocation import AllocationDelivery, AllocationDeliveryIntake, AllocationSession
from app.models.college import Campus, College
from app.models.course import CourseOffering, OfferingDurationOption
from app.models.facility import Facility
from app.models.qualification import Qualification, Unit
from app.models.student import Student, StudentGroup
from app.models.timetable import RollingTimetableWeek
from app.models.trainer import Trainer
from app.services.students import StudentServiceError

#: Weekday names in the order `date.weekday()` returns them, matching the
#: `allocation_weekday` enum the sessions are stored with.
WEEKDAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")

#: A delivery longer than this is a data fault. Expanding it would emit tens of
#: thousands of rows and hide the fault behind a hung browser.
MAX_EXPANSION_DAYS = 400

#: A rolling span and a delivery range may legitimately differ, because
#: `_match_intakes` links on date *overlap* rather than containment. Beyond this
#: the difference is worth telling the reader about.
SPAN_TOLERANCE_DAYS = 6

#: The query budget this module promises. Asserted by the tests.
TIMETABLE_QUERY_COUNT = 3
EMPTY_STATE_QUERY_COUNT = 1

_VIRTUAL_LABELS = {
    "FACE_TO_FACE_VC": "Face to Face VC",
}


def _weekday_name(day: dt.date) -> str:
    return WEEKDAYS[day.weekday()]


def _normalise_code(value: str | None) -> str:
    """Upper-cased, whitespace-collapsed — the same shape on both sides."""
    return " ".join((value or "").upper().split())


@dataclass
class _ClassRow:
    date: dt.date
    weekday: str
    start_time: str
    end_time: str
    stream: str
    delivery_mode: str
    mode_label: str
    classroom: str
    classroom_unresolved: bool
    campus: str
    campus_unresolved: bool


@dataclass
class _UnitGroup:
    """Consecutive rolling weeks delivering the same unit."""

    unit_code: str
    unit_slot: int
    week_from: dt.date
    week_to: dt.date
    classes: list[_ClassRow] = field(default_factory=list)
    unit_title: str = ""
    mode_of_delivery: str | None = None
    uoc_type: str | None = None
    span_note: str | None = None
    expansion_refused: bool = False
    allocated: bool = False


def _mode_label(delivery_mode: str, virtual_kind: str | None) -> str:
    if delivery_mode == "VIRTUAL":
        label = _VIRTUAL_LABELS.get(virtual_kind or "", "")
        return f"Virtual ({label})" if label else "Virtual"
    return "Physical"


def student_timetable(session: Session, student_pk: int) -> dict:
    """Build one student's timetable. Three queries, or one for an empty state."""
    # -- Query 1: the student and the scope that limits what they may see ----
    scope = _load_scope(session, student_pk)

    empty_reason = _empty_reason(scope)
    if empty_reason is not None:
        # Nothing further to fetch: queries 2 and 3 are never issued.
        return _envelope(scope, rows=[], empty_reason=empty_reason)

    # -- Query 2: what this intake studies ----------------------------------
    weeks = list(
        session.execute(
            select(RollingTimetableWeek)
            .where(
                RollingTimetableWeek.training_package == scope["training_package"],
                RollingTimetableWeek.intake_label == scope["intake_label"],
            )
            .order_by(RollingTimetableWeek.week_no, RollingTimetableWeek.unit_slot)
        ).scalars()
    )
    if not weeks:
        return _envelope(scope, rows=[], empty_reason="NO_ROLLING_ROWS")

    # -- Query 3: when and where, at this student's own campus ---------------
    allocations = session.execute(_allocation_query(scope)).all()

    rows = _assemble(weeks, allocations, scope)
    return _envelope(scope, rows=rows, empty_reason=None)


# ---------------------------------------------------------------------------
# Query 1
# ---------------------------------------------------------------------------


def _load_scope(session: Session, student_pk: int) -> dict:
    """The student, their course offering, and the campus that scopes the view.

    Mirrors `students._base_read_query()` rather than inventing a second join
    shape, but adds the college and campus **ids** the allocation filter needs.
    """
    row = session.execute(
        select(
            Student,
            College.id,
            College.college_short_name,
            College.college_full_name,
            Campus.id,
            Campus.campus_name,
            Campus.campus_code,
            Campus.campus_location,
            Campus.city,
            Qualification.qualification_code,
            Qualification.qualification_title,
            StudentGroup.rolling_intake_label,
            StudentGroup.group_code,
            StudentGroup.intake,
            OfferingDurationOption.duration_weeks,
        )
        # Outer: an unverified student has no offering, and must still open to
        # say so rather than claim the record does not exist.
        .outerjoin(CourseOffering, CourseOffering.id == Student.course_offering_id)
        .outerjoin(College, College.id == CourseOffering.college_id)
        .outerjoin(Campus, Campus.id == CourseOffering.campus_id)
        .outerjoin(Qualification, Qualification.id == CourseOffering.qualification_id)
        .outerjoin(StudentGroup, StudentGroup.id == Student.student_group_id)
        .outerjoin(
            OfferingDurationOption, OfferingDurationOption.id == Student.course_duration_option_id
        )
        .where(Student.id == student_pk)
    ).one_or_none()

    if row is None:
        raise StudentServiceError(404, "That student record was not found.")

    student: Student = row[0]
    qualification_code = row[9] or ""
    return {
        "student": student,
        "college_id": row[1],
        "college": row[2] or student.college_text or "",
        "campus_id": row[4],
        "campus": row[5] or student.campus_text or "",
        # Every spelling the student's own college and campus are known by, so a
        # delivery whose reference did not resolve can still be matched on the
        # text it was written as. Without this a class recorded at "Sydney"
        # appears on a Hobart student's timetable.
        "college_aliases": [value for value in (row[2], row[3]) if value],
        "campus_aliases": [value for value in (row[5], row[6], row[7], row[8]) if value],
        "qualification_code": qualification_code,
        "qualification_title": row[10],
        "intake_label": row[11],
        "group_code": row[12],
        "intake_start_date": row[13],
        "duration_weeks": row[14],
        # The rolling timetable's own CHECK guarantees the package is the first
        # three characters of the qualification code, so it is derived rather
        # than asked for — and it prunes the partitioned allocation tables.
        "training_package": qualification_code[:3].upper(),
    }


def _empty_reason(scope: dict) -> str | None:
    """Which of the three "no timetable" states applies, if any."""
    student: Student = scope["student"]
    if student.course_offering_id is None:
        # Unverified (15 September 2026): no offering, so no campus to scope a
        # timetable to until the student's suggestion resolves.
        return "UNVERIFIED"
    if student.intake_match_status == "NOT_APPLICABLE":
        return "CREDIT_TRANSFER"
    if student.intake_match_status == "TBD":
        return "NO_ROLLING_TIMETABLE"
    if not scope["intake_label"]:
        # MATCHED but no label stored: the same practical outcome.
        return "NO_ROLLING_TIMETABLE"
    return None


# ---------------------------------------------------------------------------
# Query 3
# ---------------------------------------------------------------------------


def _normalised(column):
    """The SQL equivalent of the reference normaliser.

    `btrim` alone is not enough: the Python normaliser collapses **internal**
    whitespace too, so `South  Melbourne` and `South Melbourne` compare equal.
    """
    return func.upper(func.btrim(func.regexp_replace(column, r"\s+", " ", "g")))


def _scoped(id_column, text_column, wanted_id: int, aliases: list[str]):
    """Is this delivery the student's, by identifier or by what it was written as?

    Three arms, in order of how much the row actually says:

    1. The identifier resolved and is theirs.
    2. It did not resolve, but the text matches a spelling of theirs.
    3. It did not resolve and carries no text at all — nothing to disagree with,
       so it is shown rather than hidden on the strength of a blank cell.
    """
    spellings = [value.strip() for value in aliases if value and value.strip()]
    unknown = and_(
        id_column.is_(None),
        or_(text_column.is_(None), func.btrim(text_column) == ""),
    )
    if not spellings:
        return or_(id_column == wanted_id, unknown)
    return or_(
        id_column == wanted_id,
        and_(
            id_column.is_(None),
            _normalised(text_column).in_([" ".join(value.split()).upper() for value in spellings]),
        ),
        unknown,
    )


def _allocation_query(scope: dict) -> Select:
    """Every non-quarantined class for this intake, at this student's campus.

    All four reference joins are **outer**. `allocation_calendar.py` uses inner
    joins on the same nullable foreign keys and therefore silently drops every
    delivery with an unresolved reference — the ones most needing attention.

    **The college and campus must match the student's own** — the same intake
    label runs at several campuses and for several colleges, so without this a
    student is shown every college's copy of their unit.

    An unresolved reference is matched on the **text it was written as**, not
    waved through. The `IS NULL` arm alone said only "this did not resolve", so
    a delivery recorded at "Sydney" appeared on a Hobart student's timetable —
    the campus column even said Sydney while claiming to be theirs. A delivery
    is now in scope when its id matches, or its text matches a spelling the
    student's own college or campus is known by. One that carries neither an id
    nor any text says nothing about where it belongs and is still shown, because
    excluding it would hide a class on the strength of a blank cell.

    Matching on text also means the view corrects itself as the reference data
    improves: once "Sydney" resolves to a campus, or a campus records its city,
    these rows land with the right students without a re-import.
    """
    return (
        select(
            AllocationDelivery.id,
            AllocationDelivery.start_date,
            AllocationDelivery.end_date,
            AllocationDelivery.mode_of_delivery,
            AllocationDelivery.uoc_type,
            AllocationDelivery.unit_text,
            AllocationDelivery.campus_text,
            Unit.unit_code,
            Unit.unit_title,
            Campus.campus_name,
            AllocationSession.stream,
            AllocationSession.weekday,
            AllocationSession.start_time,
            AllocationSession.end_time,
            AllocationSession.delivery_mode,
            AllocationSession.virtual_kind,
            AllocationSession.classroom_text,
            Facility.facility_reference,
        )
        .select_from(AllocationDeliveryIntake)
        .join(
            AllocationDelivery,
            (AllocationDelivery.id == AllocationDeliveryIntake.delivery_id)
            & (AllocationDelivery.training_package == AllocationDeliveryIntake.training_package),
        )
        # Inner: a delivery with no sessions has nothing to show, and its unit
        # row is Unallocated by rule 2.5.6.
        .join(
            AllocationSession,
            (AllocationSession.delivery_id == AllocationDelivery.id)
            & (AllocationSession.training_package == AllocationDelivery.training_package),
        )
        .outerjoin(Unit, Unit.id == AllocationDelivery.unit_id)
        .outerjoin(Qualification, Qualification.id == AllocationDelivery.qualification_id)
        .outerjoin(College, College.id == AllocationDelivery.college_id)
        .outerjoin(Campus, Campus.id == AllocationDelivery.campus_id)
        .outerjoin(Facility, Facility.id == AllocationSession.facility_id)
        .outerjoin(Trainer, Trainer.id == AllocationSession.trainer_id)
        .where(
            AllocationDeliveryIntake.intake_label == scope["intake_label"],
            AllocationDelivery.training_package == scope["training_package"],
            # A record an administrator rejected is never shown to a student.
            AllocationDelivery.is_quarantined.is_(False),
            _scoped(
                AllocationDelivery.college_id,
                AllocationDelivery.college_text,
                scope["college_id"],
                scope["college_aliases"],
            ),
            _scoped(
                AllocationDelivery.campus_id,
                AllocationDelivery.campus_text,
                scope["campus_id"],
                scope["campus_aliases"],
            ),
        )
        .order_by(AllocationDelivery.start_date, AllocationDelivery.id, AllocationSession.id)
    )


# ---------------------------------------------------------------------------
# Assembly — in memory, no further queries
# ---------------------------------------------------------------------------


def _assemble(weeks: list[RollingTimetableWeek], allocations: list, scope: dict) -> list[dict]:
    """Group the rolling weeks, attach the allocations, expand each class."""
    groups = _group_weeks(weeks)
    by_unit = _deliveries_by_unit(allocations)

    student: Student = scope["student"]
    rows: list[dict] = []

    for kind, group in groups:
        if kind != "UNIT":
            rows.append(
                {
                    "row_type": kind,
                    "week_from": group.week_from,
                    "week_to": group.week_to,
                    "timing": _timing(group.week_from, group.week_to, student),
                    "unit_code": None,
                    "unit_title": None,
                    "allocation_status": None,
                    "mode_of_delivery": None,
                    "uoc_type": None,
                    "span_note": None,
                    "expansion_refused": False,
                    "classes": [],
                    "unit_slot": group.unit_slot,
                }
            )
            continue

        _attach_allocations(group, by_unit.get(_normalise_code(group.unit_code), []), scope)
        rows.append(
            {
                "row_type": "UNIT",
                "week_from": group.week_from,
                "week_to": group.week_to,
                "timing": _timing(group.week_from, group.week_to, student),
                "unit_code": group.unit_code,
                "unit_title": group.unit_title,
                "allocation_status": "ALLOCATED" if group.allocated else "UNALLOCATED",
                "mode_of_delivery": group.mode_of_delivery,
                "uoc_type": group.uoc_type,
                "span_note": group.span_note,
                "expansion_refused": bool(group.expansion_refused),
                "classes": [_class_dict(item) for item in group.classes],
                "unit_slot": group.unit_slot,
            }
        )

    rows.sort(key=lambda row: (row["week_from"], row["unit_slot"]))
    return rows


def _group_weeks(weeks: list[RollingTimetableWeek]) -> list[tuple[str, _UnitGroup]]:
    """Collapse the rolling weeks into unit, break and assessment rows.

    A break does **not** end a unit: a Break is not a UNIT row, so the same unit
    resuming afterwards continues the same delivery. This mirrors
    `_first_unit_window` in `core.intake_assignment` rather than offering a
    second interpretation of it.
    """
    ordered = sorted(weeks, key=lambda week: (week.week_no, week.unit_slot))
    groups: list[tuple[str, _UnitGroup]] = []

    # Units are grouped per slot, so two units in one week stay two rows.
    open_units: dict[int, _UnitGroup] = {}
    open_special: dict[str, _UnitGroup] = {}
    last_special_week: dict[str, int] = {}

    for week in ordered:
        if week.schedule_type == "UNIT":
            code = week.unit_code or week.schedule_value
            slot = week.unit_slot
            current = open_units.get(slot)
            if current is not None and _normalise_code(current.unit_code) == _normalise_code(code):
                current.week_to = max(current.week_to, week.week_end_date)
            else:
                current = _UnitGroup(
                    unit_code=code,
                    unit_slot=slot,
                    week_from=week.week_start_date,
                    week_to=week.week_end_date,
                )
                open_units[slot] = current
                groups.append(("UNIT", current))
            continue

        # BREAK / ASSESSMENT_WEEK: consecutive weeks collapse into one row.
        kind = week.schedule_type
        previous = last_special_week.get(kind)
        current = open_special.get(kind)
        if current is not None and previous is not None and week.week_no == previous + 1:
            current.week_to = max(current.week_to, week.week_end_date)
        else:
            current = _UnitGroup(
                unit_code="",
                unit_slot=week.unit_slot,
                week_from=week.week_start_date,
                week_to=week.week_end_date,
            )
            open_special[kind] = current
            groups.append((kind, current))
        last_special_week[kind] = week.week_no

    return groups


def _deliveries_by_unit(allocations: list) -> dict[str, list]:
    """Index the allocation rows by their unit code, resolved or not.

    Matching on the **text** rather than `unit_id` is what makes an
    unresolved-unit delivery attach to the unit the student actually studies.
    Matching on the id would leave it orphaned: the unit row would read grey
    Unallocated while a fully allocated class with a real room existed.
    """
    grouped: dict[str, list] = {}
    for row in allocations:
        code = _normalise_code(row.unit_code or row.unit_text)
        if not code:
            continue
        grouped.setdefault(code, []).append(row)
    return grouped


def _attach_allocations(group: _UnitGroup, rows: list, scope: dict) -> None:
    """Expand every matched delivery into one row per real class occurrence."""
    if not rows:
        return

    by_delivery: dict[int, list] = {}
    for row in rows:
        by_delivery.setdefault(row.id, []).append(row)

    notes: list[str] = []
    for delivery_id, sessions in by_delivery.items():
        first = sessions[0]
        group.unit_title = group.unit_title or (first.unit_title or "")
        group.mode_of_delivery = group.mode_of_delivery or first.mode_of_delivery
        group.uoc_type = group.uoc_type or first.uoc_type

        start, end = first.start_date, first.end_date
        if (end - start).days > MAX_EXPANSION_DAYS:
            # A range this long is a data fault; report it rather than emitting
            # tens of thousands of rows.
            group.expansion_refused = True
            group.allocated = True
            notes.append(
                f"Delivery {delivery_id} spans {start:%d-%b-%Y} to {end:%d-%b-%Y}, "
                f"which exceeds {MAX_EXPANSION_DAYS} days and was not expanded."
            )
            continue

        # The allocation record is the actual room and trainer booking, so its
        # dates are what really happens — not the rolling week span.
        if (
            abs((start - group.week_from).days) > SPAN_TOLERANCE_DAYS
            or abs((end - group.week_to).days) > SPAN_TOLERANCE_DAYS
        ):
            notes.append(
                f"The rolling timetable places this unit from {group.week_from:%d-%b-%Y} to "
                f"{group.week_to:%d-%b-%Y}, while the allocation runs {start:%d-%b-%Y} to "
                f"{end:%d-%b-%Y}."
            )

        group.allocated = True
        for session_row in sessions:
            cursor = start
            while cursor <= end:
                if _weekday_name(cursor) == session_row.weekday:
                    group.classes.append(_build_class(cursor, session_row))
                cursor += dt.timedelta(days=1)

    if notes:
        group.span_note = " ".join(dict.fromkeys(notes))
    group.classes.sort(key=lambda item: (item.date, item.start_time, item.stream))


def _build_class(day: dt.date, row) -> _ClassRow:
    """One class occurrence, with the approved value preferred over the text."""
    classroom = row.facility_reference or row.classroom_text or ""
    classroom_unresolved = bool(not row.facility_reference and row.classroom_text)
    if not classroom:
        label = _VIRTUAL_LABELS.get(row.virtual_kind or "")
        classroom = label or "Not yet allocated"
        classroom_unresolved = False

    campus = row.campus_name or row.campus_text or ""
    campus_unresolved = bool(not row.campus_name and row.campus_text)
    if not campus:
        campus = "Not yet resolved"
        campus_unresolved = True

    return _ClassRow(
        date=day,
        weekday=_weekday_name(day),
        # Strings, never `datetime.time`: the wire carries "HH:MM".
        start_time=row.start_time.strftime("%H:%M"),
        end_time=row.end_time.strftime("%H:%M"),
        stream=row.stream,
        delivery_mode=row.delivery_mode,
        mode_label=_mode_label(row.delivery_mode, row.virtual_kind),
        classroom=classroom,
        classroom_unresolved=classroom_unresolved,
        campus=campus,
        campus_unresolved=campus_unresolved,
    )


def _class_dict(row: _ClassRow) -> dict:
    return {
        "date": row.date,
        "weekday": row.weekday,
        "start_time": row.start_time,
        "end_time": row.end_time,
        "stream": row.stream,
        "delivery_mode": row.delivery_mode,
        "mode_label": row.mode_label,
        "classroom": row.classroom,
        "classroom_unresolved": bool(row.classroom_unresolved),
        "campus": row.campus,
        "campus_unresolved": bool(row.campus_unresolved),
    }


def _timing(week_from: dt.date, week_to: dt.date, student: Student) -> str:
    """Where this row sits against the student's own enrolment dates.

    The whole intake is listed for context, but a unit the student was never
    enrolled for is marked rather than presented as though they attended it.
    """
    if student.proposed_start_date and week_to < student.proposed_start_date:
        return "BEFORE_JOINING"
    if student.proposed_end_date and week_from > student.proposed_end_date:
        return "AFTER_END"
    return "DURING"


def _envelope(scope: dict, *, rows: list[dict], empty_reason: str | None) -> dict:
    student: Student = scope["student"]
    unit_rows = [row for row in rows if row["row_type"] == "UNIT"]
    allocated = [row for row in unit_rows if row["allocation_status"] == "ALLOCATED"]
    return {
        "student": {
            "id": student.id,
            "student_id": student.student_id,
            "name": f"{student.first_name} {student.last_name or ''}".strip(),
            "status": student.status,
            "ct_student": bool(student.ct_student),
        },
        "qualification": {
            "code": scope["qualification_code"],
            "title": scope["qualification_title"],
            "duration_weeks": scope["duration_weeks"],
        },
        "intake": {
            "label": scope["intake_label"],
            "group_code": scope["group_code"],
            "match_status": student.intake_match_status,
            "start_date": scope["intake_start_date"],
        },
        "scope": {"college": scope["college"], "campus": scope["campus"]},
        "course_dates": {
            "proposed_start_date": student.proposed_start_date,
            "proposed_end_date": student.proposed_end_date,
        },
        "empty_reason": empty_reason,
        "summary": {
            "units_total": len(unit_rows),
            "units_allocated": len(allocated),
            "units_unallocated": len(unit_rows) - len(allocated),
            "classes_total": sum(len(row["classes"]) for row in unit_rows),
        },
        "rows": rows,
    }
