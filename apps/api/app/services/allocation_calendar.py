"""Calendar month view. Cost: exactly three queries."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.models.allocation import AllocationDelivery, AllocationDeliveryIntake, AllocationSession
from app.models.college import Campus, College
from app.models.course import CourseOffering
from app.models.facility import Facility
from app.models.qualification import Qualification, Unit
from app.models.student import Student, StudentGroup
from app.models.timetable import RollingTimetableWeek
from app.models.trainer import Trainer

CALENDAR_QUERY_COUNT = 3

WEEKDAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")

_STREAM_ORDER = {"THEORY": 0, "PRACTICAL": 1, "MSCRIS": 2}


def _weekday_name(day: dt.date) -> str:
    return WEEKDAYS[day.weekday()]


def _week_start(day: dt.date) -> dt.date:
    return day - dt.timedelta(days=day.weekday())


def _plural(count: int, word: str, suffix: str = "s") -> str:
    return f"{count} {word}{'' if count == 1 else suffix}"


def _merge_mscris(items: list[dict]) -> list[dict]:
    """One calendar entry per MSCRIS class, not one per unit.

    Approved 17 September 2026: every MSCRIS class day on a date with the same
    time, classroom and trainer is the same class, whatever unit, college or
    campus it was uploaded under. Those class days become one entry tagged
    MSCRIS that lists the units it covers. Two MSCRIS classes on one day whose
    time, classroom or trainer differ stay two entries: they are two classes.
    """
    groups: dict[tuple, list[dict]] = {}
    others: list[dict] = []
    for item in items:
        if item["stream"] != "MSCRIS":
            others.append(item)
            continue
        key = (item["start_time"], item["end_time"], item["classroom"], item["trainer"])
        groups.setdefault(key, []).append(item)

    merged = []
    for members in groups.values():
        members.sort(key=lambda item: (item["unit_code"], item["college"], item["campus"], item["session_id"]))
        first = members[0]
        units = {item["unit_code"] for item in members}
        not_found = any(item["not_found"] for item in members)
        merged.append(
            {
                **first,
                "session_id": min(item["session_id"] for item in members),
                "unit_code": "MSCRIS",
                "unit_title": f"{_plural(len(units), 'unit')} · {_plural(len(members), 'class', 'es')}",
                "qualification_code": ", ".join(sorted({item["qualification_code"] for item in members})),
                "college": ", ".join(sorted({item["college"] for item in members})),
                "campus": ", ".join(sorted({item["campus"] for item in members})),
                "intakes": sorted({label for item in members for label in item["intakes"]}),
                "intake_match_status": "NOT_FOUND" if not_found else first["intake_match_status"],
                "needs_allocation": any(item["needs_allocation"] for item in members),
                "not_found": not_found,
                "student_count": sum(item["student_count"] for item in members),
                "session_ids": sorted(item["session_id"] for item in members),
                "covered": [
                    {
                        "session_id": item["session_id"],
                        "delivery_id": item["delivery_id"],
                        "unit_code": item["unit_code"],
                        "unit_title": item["unit_title"],
                        "qualification_code": item["qualification_code"],
                        "college": item["college"],
                        "campus": item["campus"],
                        "intakes": item["intakes"],
                        "student_count": item["student_count"],
                    }
                    for item in members
                ],
            }
        )
    combined = others + merged
    # A stable order, so the same day reads the same way on every load.
    combined.sort(
        key=lambda item: (
            item["start_time"],
            _STREAM_ORDER.get(item["stream"], 9),
            item["unit_code"],
            item["college"],
            item["campus"],
            item["session_id"],
        )
    )
    return combined


def calendar_month(
    session: Session,
    *,
    training_package: str,
    start_date: dt.date,
    end_date: dt.date,
) -> dict:
    """Sessions, the rolling timetable's expectation, and who attends. Never per day.

    Expected units are a **weekly** figure (approved 17 September 2026): a unit
    the rolling timetable schedules in a week is expected until a Theory or
    Practical class of it falls anywhere in that week. MSCRIS does not count - it
    is one class for every college. So the queries read whole Monday-to-Sunday
    weeks even when the requested range starts or ends mid-week; only the
    requested days are returned.
    """
    package = training_package.upper()
    read_from = _week_start(start_date)
    read_to = _week_start(end_date) + dt.timedelta(days=6)

    session_stmt: Select = (
        select(
            AllocationSession.id,
            AllocationSession.training_package,
            AllocationSession.delivery_id,
            AllocationSession.stream,
            AllocationSession.weekday,
            AllocationSession.start_time,
            AllocationSession.end_time,
            AllocationSession.delivery_mode,
            AllocationSession.facility_id,
            AllocationSession.virtual_kind,
            AllocationSession.classroom_text,
            AllocationSession.trainer_id,
            AllocationSession.trainer_text,
            AllocationDelivery.college_id,
            AllocationDelivery.campus_id,
            AllocationDelivery.qualification_id,
            AllocationDelivery.duration_weeks,
            AllocationDelivery.start_date,
            AllocationDelivery.end_date,
            AllocationDelivery.intake_match_status,
            AllocationDelivery.classroom_size,
            Qualification.qualification_code,
            Qualification.qualification_title,
            Unit.unit_code,
            Unit.unit_title,
            College.college_short_name,
            Campus.campus_name,
            Facility.facility_reference,
            Trainer.trainer_name,
            func.coalesce(
                func.array_agg(AllocationDeliveryIntake.intake_label).filter(
                    AllocationDeliveryIntake.intake_label.isnot(None)
                ),
                [],
            ).label("intake_labels"),
        )
        .join(
            AllocationDelivery,
            and_(
                AllocationDelivery.id == AllocationSession.delivery_id,
                AllocationDelivery.training_package == AllocationSession.training_package,
            ),
        )
        .join(Qualification, Qualification.id == AllocationDelivery.qualification_id)
        .join(Unit, Unit.id == AllocationDelivery.unit_id)
        .join(College, College.id == AllocationDelivery.college_id)
        .join(Campus, Campus.id == AllocationDelivery.campus_id)
        .outerjoin(Facility, Facility.id == AllocationSession.facility_id)
        .outerjoin(Trainer, Trainer.id == AllocationSession.trainer_id)
        .outerjoin(
            AllocationDeliveryIntake,
            and_(
                AllocationDeliveryIntake.delivery_id == AllocationDelivery.id,
                AllocationDeliveryIntake.training_package == AllocationDelivery.training_package,
            ),
        )
        .where(
            AllocationSession.training_package == package,
            AllocationDelivery.start_date <= read_to,
            AllocationDelivery.end_date >= read_from,
            # A quarantined delivery is retained for audit but never operational.
            AllocationDelivery.is_quarantined.is_(False),
        )
        .group_by(
            AllocationSession.id,
            AllocationSession.training_package,
            AllocationSession.delivery_id,
            AllocationSession.stream,
            AllocationSession.weekday,
            AllocationSession.start_time,
            AllocationSession.end_time,
            AllocationSession.delivery_mode,
            AllocationSession.facility_id,
            AllocationSession.virtual_kind,
            AllocationSession.classroom_text,
            AllocationSession.trainer_id,
            AllocationSession.trainer_text,
            AllocationDelivery.college_id,
            AllocationDelivery.campus_id,
            AllocationDelivery.qualification_id,
            AllocationDelivery.duration_weeks,
            AllocationDelivery.start_date,
            AllocationDelivery.end_date,
            AllocationDelivery.intake_match_status,
            AllocationDelivery.classroom_size,
            Qualification.qualification_code,
            Qualification.qualification_title,
            Unit.unit_code,
            Unit.unit_title,
            College.college_short_name,
            Campus.campus_name,
            Facility.facility_reference,
            Trainer.trainer_name,
        )
    )
    session_rows = session.execute(session_stmt).all()

    rolling_stmt = select(
        RollingTimetableWeek.week_start_date,
        RollingTimetableWeek.week_end_date,
        RollingTimetableWeek.qualification_code,
        RollingTimetableWeek.intake_label,
        RollingTimetableWeek.unit_code,
    ).where(
        RollingTimetableWeek.training_package == package,
        RollingTimetableWeek.week_start_date <= read_to,
        RollingTimetableWeek.week_end_date >= read_from,
        RollingTimetableWeek.schedule_type == "UNIT",
    )
    rolling_rows = session.execute(rolling_stmt).all()

    # Who attends: an active student is in a class when their college, campus
    # and qualification are the class's, and their rolling intake is one the
    # class was matched to - the same join a student's own timetable uses.
    attendance_stmt = (
        select(
            CourseOffering.college_id,
            CourseOffering.campus_id,
            CourseOffering.qualification_id,
            StudentGroup.rolling_intake_label,
            func.count(Student.id),
        )
        .join(CourseOffering, CourseOffering.id == Student.course_offering_id)
        .join(StudentGroup, StudentGroup.id == Student.student_group_id)
        .where(
            Student.is_deleted.is_(False),
            Student.status == "ACTIVE",
            StudentGroup.rolling_intake_label.isnot(None),
        )
        .group_by(
            CourseOffering.college_id,
            CourseOffering.campus_id,
            CourseOffering.qualification_id,
            StudentGroup.rolling_intake_label,
        )
    )
    attendance = {
        (college, campus, qualification, label): count
        for college, campus, qualification, label, count in session.execute(attendance_stmt).all()
    }

    # Every day of the weeks read, so the weekly figure sees the whole week.
    by_day: dict[dt.date, list[dict]] = {}
    cursor = read_from
    while cursor <= read_to:
        weekday = _weekday_name(cursor)
        items = []
        for row in session_rows:
            if row.weekday != weekday:
                continue
            if cursor < row.start_date or cursor > row.end_date:
                continue
            room = row.facility_reference or row.classroom_text or ""
            trainer = row.trainer_name or row.trainer_text or ""
            # `and`/`or` return the last operand, not a boolean, so without
            # bool() this yields None or the trainer's name and Pydantic rejects
            # it — a 500 on exactly the sessions the flag exists to highlight.
            needs_allocation = bool(
                (row.delivery_mode == "PHYSICAL" and row.facility_id is None)
                or (row.stream != "MSCRIS" and row.trainer_id is None and row.trainer_text)
            )
            intakes = sorted({label for label in (row.intake_labels or []) if label})
            items.append(
                {
                    "session_id": row.id,
                    "delivery_id": row.delivery_id,
                    "stream": row.stream,
                    "weekday": row.weekday,
                    "start_time": row.start_time.strftime("%H:%M"),
                    "end_time": row.end_time.strftime("%H:%M"),
                    "unit_code": row.unit_code,
                    "unit_title": row.unit_title,
                    "qualification_code": row.qualification_code,
                    "college": row.college_short_name,
                    "campus": row.campus_name,
                    "duration_weeks": row.duration_weeks,
                    "unit_start_date": row.start_date.isoformat(),
                    "unit_end_date": row.end_date.isoformat(),
                    "classroom": room,
                    "trainer": trainer,
                    "delivery_mode": row.delivery_mode,
                    "virtual_kind": row.virtual_kind,
                    "intakes": intakes,
                    "intake_match_status": row.intake_match_status,
                    "needs_allocation": needs_allocation,
                    "not_found": row.intake_match_status == "NOT_FOUND",
                    "student_count": sum(
                        attendance.get((row.college_id, row.campus_id, row.qualification_id, label), 0)
                        for label in intakes
                    ),
                    "session_ids": [row.id],
                    "covered": [],
                }
            )
        by_day[cursor] = items
        cursor += dt.timedelta(days=1)

    # Units with a Theory or Practical class anywhere in each week.
    taught: dict[dt.date, set[str]] = defaultdict(set)
    for day, items in by_day.items():
        for item in items:
            if item["stream"] != "MSCRIS":
                taught[_week_start(day)].add(item["unit_code"])

    # Units the rolling timetable schedules in each week that nobody teaches yet.
    expected: dict[dt.date, dict[str, dict]] = defaultdict(dict)
    week = read_from
    while week <= read_to:
        week_end = week + dt.timedelta(days=6)
        for row in rolling_rows:
            if not row.unit_code or row.unit_code in taught[week]:
                continue
            if row.week_start_date > week_end or row.week_end_date < week:
                continue
            entry = expected[week].setdefault(
                row.unit_code, {"unit_code": row.unit_code, "qualifications": set(), "intakes": set()}
            )
            entry["qualifications"].add(row.qualification_code)
            entry["intakes"].add(row.intake_label)
        week += dt.timedelta(days=7)

    days = []
    cursor = start_date
    while cursor <= end_date:
        items = by_day[cursor]
        week_expected = sorted(expected[_week_start(cursor)].values(), key=lambda entry: entry["unit_code"])
        days.append(
            {
                "date": cursor.isoformat(),
                "weekday": _weekday_name(cursor),
                "sessions": _merge_mscris(items),
                # Unique units with a Theory or Practical class that day.
                "allocated_unit_count": len(
                    {item["unit_code"] for item in items if item["stream"] != "MSCRIS"}
                ),
                # The week's figure, repeated on each of its days.
                "expected_unit_count": len(week_expected),
                "expected_units": [
                    {
                        "unit_code": entry["unit_code"],
                        "qualification_codes": sorted(entry["qualifications"]),
                        "intake_labels": sorted(entry["intakes"]),
                    }
                    for entry in week_expected
                ],
            }
        )
        cursor += dt.timedelta(days=1)
    return {
        "training_package": package,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "days": days,
        "query_cost": CALENDAR_QUERY_COUNT,
        "empty": not any(day["sessions"] for day in days),
    }
