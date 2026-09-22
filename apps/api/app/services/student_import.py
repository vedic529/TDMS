"""Bulk student import: parse, stage, review, decide, apply.

The Schema v1 staging tables hold the upload; nothing reaches `students` until
the batch is confirmed (BULK-02, rule 2.3). Reference resolution, intake
derivation and duplicate detection all run in **bulk** — one query for the
rolling timetable, one for existing students, one lookup load per import — so a
thousand-row file does not issue a thousand queries (rule 2.9).

An unresolved College / Campus / Qualification - or a combination no approved
course offering holds - blocks the confirmation until the user corrects it,
resolves it inline, or raises a suggestion (approved 15 September 2026). A raised
row is **stored unverified**: `course_offering_id` stays NULL, the three values
are kept as written, and the student is completed when the suggestion resolves.
There is no exception path: an unmatched value is never waved through.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, func, insert, or_, select, tuple_
from sqlalchemy.orm import Session

from app.models.college import Campus, CampusSourceAddress, College, CollegeCampus
from app.models.course import CourseOffering, OfferingDurationOption
from app.models.import_batch import ImportBatch, ImportRowIssue, ImportStagedRow
from app.models.qualification import Qualification
from app.models.student import Student, StudentGroup
from app.models.timetable import RollingTimetableWeek
from app.models.user import User
from app.core import intake_assignment
from app.core.intake_assignment import assign_intake, build_windows
from app.services import students as student_service
from app.services.activity import record_activity
from app.services.reference_suggestions import raise_reference_suggestion

STUDENT_IMPORT_PAGE = "Page 2B - Bulk Student Import"

# -- Template columns (rule 2.2), matched by name --------------------------
C_STUDENT_ID = "Student ID"
C_FIRST = "First Name"
C_LAST = "Last Name"
C_COLLEGE = "College"
C_CAMPUS = "Campus"
C_QUAL = "Qualification"
C_CT = "CT Student"
C_COE = "CoE / Non-CoE"
C_START = "Proposed Start Date"
C_END = "Proposed End Date"
C_PERSONAL_EMAIL = "Personal Email"
C_PHONE = "Primary Phone"
C_STATUS = "Status"

REQUIRED_COLUMNS = (C_STUDENT_ID, C_FIRST, C_COLLEGE, C_CAMPUS, C_QUAL, C_CT, C_COE, C_START, C_END)
OPTIONAL_COLUMNS = (C_LAST, C_PERSONAL_EMAIL, C_PHONE, C_STATUS)
IGNORED_COLUMNS = ("Group",)  # present-but-derived: reported as a note, never an error

#: Header text (whitespace-collapsed, lowercased) -> canonical column.
_HEADER_ALIASES = {
    "student id": C_STUDENT_ID,
    "first name": C_FIRST,
    "last name": C_LAST,
    "college": C_COLLEGE,
    "campus": C_CAMPUS,
    "qualification": C_QUAL,
    "ct student": C_CT,
    "coe / non-coe": C_COE,
    "coe/non-coe": C_COE,
    "coe / noncoe": C_COE,
    "coe non-coe": C_COE,
    "proposed start date": C_START,
    "proposed end date": C_END,
    "personal email": C_PERSONAL_EMAIL,
    "primary phone": C_PHONE,
    "status": C_STATUS,
    "group": "Group",
}

_COE_VALUES = {"coe": "COE", "non-coe": "NON_COE", "noncoe": "NON_COE", "non coe": "NON_COE"}
_CT_TRUE = {"yes", "y", "true"}
_CT_FALSE = {"no", "n", "false"}
_STATUS_VALUES = {"ACTIVE", "COMPLETED", "CANCELLED", "NOT_YET_STARTED"}

# Staged row statuses (staged_row_status enum).
READY = "READY"
NEEDS_CORRECTION = "NEEDS_CORRECTION"
DUPLICATE = "DUPLICATE"
UNMATCHED_REFERENCE = "UNMATCHED_REFERENCE"
EXCLUDED = "EXCLUDED_BY_USER"

_AMBIGUOUS_ISO_RE = re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$")


class StudentImportError(Exception):
    """A file-level refusal (rule Appendix B 8–9), mapped to HTTP 400."""


def _norm_header(text: str) -> str:
    return " ".join(str(text or "").split()).lower()


def _clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value).strip()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _read_tabular(file_name: str, payload: bytes) -> tuple[list[object], list[list[object]]]:
    """Return (header cells, data rows) from a CSV or XLSX upload.

    Cells are returned as their native type where possible so a real Excel date
    cell survives as a date (check P3); text is parsed day-first (check P2).
    """
    lower = file_name.lower()
    if lower.endswith(".csv"):
        rows = list(csv.reader(io.StringIO(payload.decode("utf-8-sig"))))
        if not rows:
            return [], []
        return list(rows[0]), [list(r) for r in rows[1:]]
    if lower.endswith(".xlsx"):
        import openpyxl

        workbook = openpyxl.load_workbook(io.BytesIO(payload), data_only=True, read_only=True)
        try:
            values = list(workbook.worksheets[0].iter_rows(values_only=True))
        finally:
            workbook.close()
        if not values:
            return [], []
        return list(values[0]), [list(r) for r in values[1:]]
    raise StudentImportError("The file must be a CSV or XLSX workbook.")


def _map_headers(header_cells: list[object]) -> tuple[dict[str, int], bool]:
    """Map canonical columns to indexes. Refuse the file on trouble (Appendix B).

    Returns (columns, group_present). Raises StudentImportError with the offending
    name for an unrecognised header or a missing required column.
    """
    columns: dict[str, int] = {}
    group_present = False
    unknown: list[str] = []
    for index, cell in enumerate(header_cells):
        name = _norm_header(cell)
        if not name:
            continue
        canonical = _HEADER_ALIASES.get(name)
        if canonical is None:
            unknown.append(str(cell).strip())
            continue
        if canonical == "Group":
            group_present = True
            continue
        columns.setdefault(canonical, index)
    if unknown:
        raise StudentImportError(
            "Unrecognised column(s): " + ", ".join(unknown) + ". Remove them and upload again."
        )
    missing = [name for name in REQUIRED_COLUMNS if name not in columns]
    if missing:
        raise StudentImportError("Missing required column(s): " + ", ".join(missing) + ".")
    return columns, group_present


def _cell(row: list[object], columns: dict[str, int], name: str) -> object:
    index = columns.get(name)
    if index is None or index >= len(row):
        return ""
    return row[index]


def parse_day_first_date(value: object) -> tuple[dt.date | None, str | None]:
    """Parse a proposed date. Returns (date, error). Day-first, never guessed."""
    if isinstance(value, dt.datetime):
        return value.date(), None
    if isinstance(value, dt.date):
        return value, None
    text = _clean(value)
    if not text:
        return None, "is required"
    # A real ISO date is accepted (some exports emit it) but a bare DD-MM style is
    # always read day-first.
    if _AMBIGUOUS_ISO_RE.match(text):
        try:
            return dt.date.fromisoformat(text), None
        except ValueError:
            return None, f"{text!r} is not a real date"
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%d-%m-%y", "%d/%m/%y"):
        try:
            return dt.datetime.strptime(text, fmt).date(), None
        except ValueError:
            continue
    return None, f"{text!r} is not a valid DD-MM-YYYY date"


# ---------------------------------------------------------------------------
# Reference lookups (loaded once per import — rule 2.9, check E2)
# ---------------------------------------------------------------------------


@dataclass
class Lookups:
    college_by_name: dict[str, int]
    campus_by_name: dict[str, int]
    qual_by_key: dict[str, tuple[int, str]]  # key -> (id, qualification_code)
    qual_code_by_id: dict[int, str]
    college_campus: set[tuple[int, int]]
    offering: dict[tuple[int, int, int], int]  # (college, campus, qual) -> offering id
    college_by_id: dict[int, College]


def _load_lookups(session: Session) -> Lookups:
    colleges = list(session.execute(select(College)).scalars())
    college_by_name: dict[str, int] = {}
    for c in colleges:
        college_by_name[c.college_full_name.strip().upper()] = c.id
        college_by_name[c.college_short_name.strip().upper()] = c.id
    campuses = list(session.execute(select(Campus)).scalars())
    campus_by_name: dict[str, int] = {}
    for cam in campuses:
        campus_by_name[cam.campus_name.strip().upper()] = cam.id
        if cam.campus_location:
            campus_by_name.setdefault(cam.campus_location.strip().upper(), cam.id)
    # Every recorded spelling of a campus, not just its name and current
    # address. `campus_source_addresses` is where the project already keeps the
    # forms a site is written in — the facility import has read it since it was
    # built — and reading it here is what stops a student file spelling like
    # `Quay Street` raising a suggestion for a campus TDMS already knows.
    #
    # `setdefault`, so a recorded spelling never displaces a campus's own name.
    for alias in session.execute(select(CampusSourceAddress)).scalars():
        if alias.source_address:
            campus_by_name.setdefault(alias.source_address.strip().upper(), alias.campus_id)
    qual_by_key: dict[str, tuple[int, str]] = {}
    qual_code_by_id: dict[int, str] = {}
    for q in session.execute(select(Qualification)).scalars():
        if q.qualification_code:
            qual_by_key[q.qualification_code.strip().upper()] = (q.id, q.qualification_code)
            qual_code_by_id[q.id] = q.qualification_code
        if q.qualification_title:
            qual_by_key.setdefault(q.qualification_title.strip().upper(), (q.id, q.qualification_code))
    college_campus = {
        (link.college_id, link.campus_id)
        for link in session.execute(select(CollegeCampus)).scalars()
    }
    offering = {
        (o.college_id, o.campus_id, o.qualification_id): o.id
        for o in session.execute(
            select(CourseOffering).where(CourseOffering.is_deleted.is_(False))
        ).scalars()
    }
    return Lookups(
        college_by_name=college_by_name,
        campus_by_name=campus_by_name,
        qual_by_key=qual_by_key,
        qual_code_by_id=qual_code_by_id,
        college_campus=college_campus,
        offering=offering,
        college_by_id={c.id: c for c in colleges},
    )


# ---------------------------------------------------------------------------
# Row evaluation
# ---------------------------------------------------------------------------


@dataclass
class _Issue:
    field_name: str
    message: str
    issue_status: str  # REFUSE_ROW | BLOCK | NOTE


@dataclass
class _Eval:
    """Everything worked out for one staged row, ready to persist and to apply."""

    student_id: str
    first_name: str
    last_name: str | None
    coe_status: str | None
    ct_student: bool | None
    status: str
    start_date: dt.date | None
    end_date: dt.date | None
    personal_email: str | None
    phone: str | None
    college_id: int | None = None
    campus_id: int | None = None
    qualification_id: int | None = None
    qualification_code: str | None = None
    offering_id: int | None = None
    duration_weeks: int | None = None
    intake_label: str | None = None
    group_code: str | None = None
    intake_start_date: dt.date | None = None
    intake_match_status: str | None = None
    duplicate_scope: str | None = None
    existing_student_id: int | None = None
    # Set when a decision means the row will not be written but does not block:
    # an unresolved reference raised or excepted, or a same-qualification
    # duplicate resolved by keeping the stored record.
    force_excluded: bool = False
    # A reference was raised as a suggestion: the row is written with no
    # offering, keeping its values as text until the suggestion resolves.
    unverified: bool = False
    row_status: str = READY
    issues: list[_Issue] = field(default_factory=list)


def _resolve_references(values: dict, lookups: Lookups, row: ImportStagedRow, ev: _Eval) -> None:
    """Resolve College, Campus, Qualification and the offering, honouring choices."""
    college_raw = (values.get(C_COLLEGE) or "").strip()
    campus_raw = (values.get(C_CAMPUS) or "").strip()
    qual_raw = (values.get(C_QUAL) or "").strip()

    # College
    ev.college_id = row.resolved_college_id or lookups.college_by_name.get(college_raw.upper())
    if college_raw and ev.college_id is None:
        _reference_issue(row, ev, "college", C_COLLEGE, college_raw, "College is not an approved record.")

    # Campus
    ev.campus_id = row.resolved_campus_id or lookups.campus_by_name.get(campus_raw.upper())
    if campus_raw and ev.campus_id is None:
        _reference_issue(row, ev, "campus", C_CAMPUS, campus_raw, "Campus is not an approved record.")
    elif ev.college_id and ev.campus_id and (ev.college_id, ev.campus_id) not in lookups.college_campus:
        _reference_issue(
            row, ev, "campus", C_CAMPUS, campus_raw,
            "Campus is not approved for the named college.",
        )
        ev.campus_id = None

    # Qualification. An already-resolved id is looked up by id — never carried
    # over from `ev`, which has not been populated yet at this point. Reading it
    # here would blank the qualification code on every re-validation and silently
    # drop the derived intake.
    resolved_qual = None
    if row.resolved_qualification_id:
        code = lookups.qual_code_by_id.get(row.resolved_qualification_id)
        if code is not None:
            resolved_qual = (row.resolved_qualification_id, code)
    if resolved_qual is None:
        resolved_qual = lookups.qual_by_key.get(qual_raw.upper())
    if resolved_qual is not None:
        ev.qualification_id, ev.qualification_code = resolved_qual
    elif qual_raw:
        _reference_issue(row, ev, "qualification", C_QUAL, qual_raw, "Qualification is not an approved record.")

    # Offering — needs all three. A combination no approved offering holds is an
    # unmatched value like any other (15 September 2026): raised as a
    # qualification suggestion, whose Add places the qualification at this
    # college and campus.
    if ev.college_id and ev.campus_id and ev.qualification_id:
        ev.offering_id = lookups.offering.get((ev.college_id, ev.campus_id, ev.qualification_id))
        if ev.offering_id is None:
            _reference_issue(
                row,
                ev,
                "qualification",
                C_QUAL,
                qual_raw,
                "No approved course offering exists for this College, Campus and Qualification.",
            )


def _reference_issue(row: ImportStagedRow, ev: _Eval, entity: str, field_name: str, value: str, message: str) -> None:
    """Record an unresolved reference and its per-entity decision state (rule 2.4).

    Raised, the row no longer blocks and is written unverified (15 September
    2026). An EXCEPT choice is not honoured: an unmatched value is never accepted
    as an exception, so the row still blocks.
    """
    choice = getattr(row, f"{entity}_choice", None)
    if choice == "RAISE":
        ev.unverified = True
        ev.issues.append(
            _Issue(
                field_name,
                f"{message} Raised as a suggestion - stored unverified until it is resolved.",
                "NOTE",
            )
        )
        return
    ev.issues.append(_Issue(field_name, f"{message} Correct it, resolve it, or raise a suggestion.", "BLOCK"))


def _rule_issue(row: ImportStagedRow, ev: _Eval, field_name: str, message: str) -> None:
    """A predefined rule broken by a row that can still be stored (15 September 2026).

    The same three choices as every import: accept it as an exception for this
    import only, exclude the row, or correct it. The acceptance is held on the
    staged row, so it goes with the batch.
    """
    if (row.working_values or {}).get("_accepted_exception"):
        ev.issues.append(_Issue(field_name, f"{message} Accepted as an exception for this import.", "ACCEPTED"))
    else:
        ev.issues.append(
            _Issue(
                field_name,
                f"{message} Correct it, exclude the row, or accept it as an exception for this import.",
                "EXCEPTION",
            )
        )


def _evaluate(
    row: ImportStagedRow,
    lookups: Lookups,
    windows_by_pair: dict[tuple[str, int], list],
    existing_by_student: dict[str, list[Student]],
    seen_offerings: dict[tuple[str, int], int],
) -> _Eval:
    """Validate, resolve, derive intake, detect duplicates for one staged row."""
    values = {
        C_STUDENT_ID: row.student_id_value,
        C_FIRST: row.first_name_value,
        C_LAST: row.last_name_value,
        C_COLLEGE: row.college_value,
        C_CAMPUS: row.campus_value,
        C_QUAL: row.qualification_value,
        C_CT: row.ct_student_value,
        C_COE: row.coe_status_value,
        C_START: row.proposed_start_date_value,
        C_END: row.proposed_end_date_value,
        C_PERSONAL_EMAIL: row.personal_email_value,
        C_PHONE: row.primary_phone_value,
        C_STATUS: row.status_value,
    }
    ev = _Eval(
        student_id=(values[C_STUDENT_ID] or "").strip(),
        first_name=(values[C_FIRST] or "").strip(),
        last_name=(values[C_LAST] or "").strip() or None,
        coe_status=None,
        ct_student=None,
        status="ACTIVE",
        start_date=None,
        end_date=None,
        personal_email=(values[C_PERSONAL_EMAIL] or "").strip() or None,
        phone=(values[C_PHONE] or "").strip() or None,
    )

    # -- Field validation (Appendix B, refuse the row) ---------------------
    if not ev.student_id:
        ev.issues.append(_Issue(C_STUDENT_ID, "Student ID is required.", "REFUSE_ROW"))
    if not ev.first_name:
        ev.issues.append(_Issue(C_FIRST, "First Name is required.", "REFUSE_ROW"))
    for field_name, raw in ((C_COLLEGE, values[C_COLLEGE]), (C_CAMPUS, values[C_CAMPUS]), (C_QUAL, values[C_QUAL])):
        if not (raw or "").strip():
            ev.issues.append(_Issue(field_name, f"{field_name} is required.", "REFUSE_ROW"))

    coe_raw = (values[C_COE] or "").strip().lower()
    ev.coe_status = _COE_VALUES.get(coe_raw)
    if ev.coe_status is None:
        ev.issues.append(_Issue(C_COE, "CoE / Non-CoE must be CoE or Non-CoE.", "REFUSE_ROW"))

    ct_raw = (values[C_CT] or "").strip().lower()
    if ct_raw in _CT_TRUE:
        ev.ct_student = True
    elif ct_raw in _CT_FALSE:
        ev.ct_student = False
    else:
        ev.issues.append(_Issue(C_CT, "CT Student must be Yes or No.", "REFUSE_ROW"))

    status_raw = (values[C_STATUS] or "").strip().upper().replace(" ", "_")
    if not status_raw:
        ev.status = "ACTIVE"
    elif status_raw in _STATUS_VALUES:
        ev.status = status_raw
    else:
        ev.issues.append(_Issue(C_STATUS, "Status is not an approved value.", "REFUSE_ROW"))

    ev.start_date, start_err = parse_day_first_date(values[C_START])
    if start_err:
        ev.issues.append(_Issue(C_START, f"Proposed Start Date {start_err}.", "REFUSE_ROW"))
    ev.end_date, end_err = parse_day_first_date(values[C_END])
    if end_err:
        ev.issues.append(_Issue(C_END, f"Proposed End Date {end_err}.", "REFUSE_ROW"))
    if ev.start_date and ev.end_date and ev.end_date <= ev.start_date:
        _rule_issue(row, ev, C_END, "Proposed End Date must be after Proposed Start Date.")

    # -- Reference resolution (rule 2.4) -----------------------------------
    _resolve_references(values, lookups, row, ev)

    # -- Intake and group (rule 2.5) ---------------------------------------
    if ev.ct_student:
        ev.intake_match_status = "NOT_APPLICABLE"
    # An intake belongs to an offering, so an unverified row has none until it
    # is completed.
    elif ev.offering_id and ev.qualification_code and ev.start_date and ev.end_date and ev.end_date > ev.start_date:
        # The duration used to find the rolling loop. A user-chosen approved
        # Course Duration Option wins over the one derived from the dates; the
        # dates themselves are never rewritten (OD-08).
        ev.duration_weeks = row.duration_override_weeks or student_service.inclusive_course_weeks(
            ev.start_date, ev.end_date
        )
        windows = windows_by_pair.get((ev.qualification_code.upper(), ev.duration_weeks), [])
        assignment = assign_intake(windows, ev.start_date)
        if assignment.status == intake_assignment.MATCHED:
            ev.intake_match_status = "MATCHED"
            ev.intake_label = assignment.intake_label
            ev.group_code = assignment.intake_group
            ev.intake_start_date = assignment.intake_start_date
        elif assignment.status == intake_assignment.CONFLICT:
            # Accepted, the student is stored with Intake TBD.
            _rule_issue(
                row,
                ev,
                C_QUAL,
                "Two intakes' first units run in this student's start week — the rolling "
                f"timetable is inconsistent: {', '.join(assignment.conflict_labels)}.",
            )
        else:  # TBD — report, and store
            ev.intake_match_status = "TBD"
            ev.issues.append(
                _Issue(C_QUAL, "No rolling timetable for this qualification and duration — Intake is TBD.", "NOTE")
            )

    # -- Duplicates (rule 2.6) ---------------------------------------------
    _detect_duplicates(row, ev, existing_by_student, seen_offerings)

    ev.row_status = _decide_status(row, ev)
    return ev


def _detect_duplicates(
    row: ImportStagedRow,
    ev: _Eval,
    existing_by_student: dict[str, list[Student]],
    seen_offerings: dict[tuple[str, int], int],
) -> None:
    if not ev.student_id:
        return
    if not ev.offering_id and not ev.unverified:
        return

    # Within-file: the same Student ID + offering appearing twice is a duplicate.
    # An unverified row has no offering yet and counts as one, the way the
    # database counts a NULL offering (`postgresql_nulls_not_distinct`).
    seen_key = (ev.student_id, ev.offering_id or 0)
    if seen_key in seen_offerings:
        ev.duplicate_scope = "SAME_QUALIFICATION"
        ev.issues.append(_Issue(C_STUDENT_ID, "This Student ID and offering already appears in this file.", "BLOCK_DUP"))
        return

    stored = existing_by_student.get(ev.student_id, [])
    if ev.offering_id:
        same_qual = [s for s in stored if s.course_offering_id == ev.offering_id or _same_qualification(s, ev)]
    else:
        same_qual = [s for s in stored if s.course_offering_id is None]
    other_qual = [s for s in stored if s not in same_qual]

    if same_qual:
        ev.duplicate_scope = "SAME_QUALIFICATION"
        ev.existing_student_id = same_qual[0].id
        row.existing_student_id = same_qual[0].id
        if row.duplicate_decision == "KEEP_STORED":
            # The incoming row is excluded; the stored record is left untouched.
            ev.force_excluded = True
        elif row.duplicate_decision == "KEEP_INCOMING":
            pass  # written as an update to the stored record at apply time
        else:
            ev.issues.append(_Issue(C_STUDENT_ID, "This Student ID already holds a record in the same qualification. Choose which to keep.", "BLOCK_DUP"))
    elif other_qual:
        ev.duplicate_scope = "DIFFERENT_QUALIFICATION"
        active = next((s for s in other_qual if s.status == "ACTIVE"), other_qual[0])
        ev.existing_student_id = active.id
        row.existing_student_id = active.id
        chosen = (row.status_value or ev.status or "").upper().replace(" ", "_")
        existing_new = (row.existing_status_value or active.status or "").upper().replace(" ", "_")
        if not row.status_value:
            ev.issues.append(_Issue(C_STATUS, "This Student ID is enrolled in another qualification. Set a status for each enrolment.", "BLOCK_DUP"))
        elif chosen == existing_new:
            ev.issues.append(_Issue(C_STATUS, "The two enrolments must have different statuses.", "BLOCK_DUP"))
        elif chosen == "ACTIVE" and existing_new == "ACTIVE":
            ev.issues.append(_Issue(C_STATUS, "Only one enrolment may be ACTIVE.", "BLOCK_DUP"))
        else:
            ev.status = chosen


def _same_qualification(stored: Student, ev: _Eval) -> bool:
    # The stored record's qualification is reachable via its offering; the caller
    # supplies offering matches. A cross-offering same-qualification match would
    # need the stored offering's qualification, which we compare below.
    return getattr(stored, "_qualification_id", None) == ev.qualification_id


def _decide_status(row: ImportStagedRow, ev: _Eval) -> str:
    # An excluded row is dropped whatever else is wrong with it — exclusion is a
    # valid way to resolve a bad or duplicated row (check P12). The issues stay
    # recorded on the row for reference.
    if row.excluded_by_user or ev.force_excluded:
        return EXCLUDED
    kinds = {issue.issue_status for issue in ev.issues}
    if "REFUSE_ROW" in kinds or "EXCEPTION" in kinds:
        return NEEDS_CORRECTION
    if "BLOCK_DUP" in kinds:
        return DUPLICATE
    if "BLOCK" in kinds:
        return UNMATCHED_REFERENCE
    return READY


def _persist_eval(row: ImportStagedRow, ev: _Eval) -> None:
    """Copy the evaluation onto the staged row and rebuild its issues."""
    row.resolved_college_id = ev.college_id
    row.resolved_campus_id = ev.campus_id
    row.resolved_qualification_id = ev.qualification_id
    row.resolved_offering_id = ev.offering_id
    row.derived_intake_label = ev.intake_label
    row.derived_group_code = ev.group_code
    row.intake_match_status = ev.intake_match_status
    row.duplicate_scope = ev.duplicate_scope
    row.duplicate_detected = ev.duplicate_scope is not None
    row.status = ev.row_status
    row.issues = [
        ImportRowIssue(field_name=i.field_name, message=i.message, issue_status=i.issue_status)
        for i in ev.issues
    ]


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------


def _bulk_context(session: Session, qualification_codes: set[str], student_ids: set[str]):
    """One rolling-timetable query and one existing-students query (rule 2.9).

    Every duration for the file's qualifications is fetched, not only the ones
    the dates imply. That still costs a single query, and it is what lets the
    review offer the durations a TBD row could be resolved to.
    """
    windows_by_pair: dict[tuple[str, int], list] = {}
    if qualification_codes:
        weeks = list(
            session.execute(
                select(RollingTimetableWeek).where(
                    func.upper(RollingTimetableWeek.qualification_code).in_(qualification_codes)
                )
            ).scalars()
        )
        windows_by_pair = build_windows(weeks)

    existing_by_student: dict[str, list[Student]] = {}
    if student_ids:
        stored = list(
            session.execute(
                select(Student, CourseOffering.qualification_id)
                # Outer: an unverified student has no offering and is still a
                # record this Student ID holds.
                .outerjoin(CourseOffering, CourseOffering.id == Student.course_offering_id)
                .where(Student.student_id.in_(student_ids), Student.is_deleted.is_(False))
            ).all()
        )
        for record, qualification_id in stored:
            record._qualification_id = qualification_id  # noqa: SLF001 - cache for same-qual test
            existing_by_student.setdefault(record.student_id, []).append(record)
    return windows_by_pair, existing_by_student


def stage_file(
    session: Session, *, user: User, file_name: str, payload: bytes
) -> ImportBatch:
    """Parse a file into the staging area and evaluate every row. Writes no student."""
    header_cells, data_rows = _read_tabular(file_name, payload)
    if not header_cells:
        raise StudentImportError("The file is empty.")
    columns, group_present = _map_headers(header_cells)
    data_rows = [r for r in data_rows if any(_clean(c) for c in r)]
    if not data_rows:
        raise StudentImportError("The file has no data rows.")

    now = dt.datetime.now(dt.timezone.utc)
    batch = ImportBatch(
        batch_reference=f"SIMP-{now:%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}",
        file_name=file_name,
        file_size_bytes=len(payload),
        uploaded_at=now,
        uploaded_by_user_id=user.id,
        row_count=len(data_rows),
        status="STAGED",
    )
    session.add(batch)
    session.flush()

    lookups = _load_lookups(session)

    # Build the staged rows as transient objects, evaluate them, THEN add and
    # flush once. Evaluating before the insert means every derived and resolved
    # value is set on the row before it is written, so staging is one multi-row
    # insert (rows) plus one for their issues — never an update per row. That is
    # what keeps the query cost flat as the file grows (rule 2.9, checks E1/E3).
    staged = [
        ImportStagedRow(
            import_batch_id=batch.id,
            source_row_number=offset,
            raw_values={name: _clean(_cell(raw, columns, name)) for name in columns},
            student_id_value=_clean(_cell(raw, columns, C_STUDENT_ID)),
            first_name_value=_clean(_cell(raw, columns, C_FIRST)),
            last_name_value=_clean(_cell(raw, columns, C_LAST)),
            college_value=_clean(_cell(raw, columns, C_COLLEGE)),
            campus_value=_clean(_cell(raw, columns, C_CAMPUS)),
            qualification_value=_clean(_cell(raw, columns, C_QUAL)),
            coe_status_value=_clean(_cell(raw, columns, C_COE)),
            ct_student_value=_clean(_cell(raw, columns, C_CT)),
            status_value=_clean(_cell(raw, columns, C_STATUS)) or None,
            # Dates kept as text: a staged row exists because it may be invalid.
            proposed_start_date_value=_clean(_cell(raw, columns, C_START)),
            proposed_end_date_value=_clean(_cell(raw, columns, C_END)),
            personal_email_value=_clean(_cell(raw, columns, C_PERSONAL_EMAIL)),
            primary_phone_value=_clean(_cell(raw, columns, C_PHONE)),
            status=NEEDS_CORRECTION,
        )
        for offset, raw in enumerate(data_rows, start=2)
    ]
    _evaluate_batch(session, staged, lookups, group_present)
    session.add_all(staged)
    session.flush()
    return batch


def _evaluate_batch(
    session: Session, staged: list[ImportStagedRow], lookups: Lookups, group_present: bool = False
) -> None:
    """Evaluate every staged row using one rolling query and one students query."""
    # First light pass to collect the qualifications and Student IDs, so the two
    # bulk queries can be issued once.
    codes: set[str] = set()
    student_ids: set[str] = set()
    for row in staged:
        sid = (row.student_id_value or "").strip()
        if sid:
            student_ids.add(sid)
        qual = lookups.qual_by_key.get((row.qualification_value or "").strip().upper())
        if qual and qual[1]:
            codes.add(qual[1].upper())

    windows_by_pair, existing_by_student = _bulk_context(session, codes, student_ids)

    # Every row is re-evaluated from its working values and decision fields, so
    # a correction anywhere keeps the whole preview current. Sticky exclusion is
    # the `excluded_by_user` flag, not a skipped pass (checks P11, P12).
    seen_offerings: dict[tuple[str, int], int] = {}
    for row in staged:
        ev = _evaluate(row, lookups, windows_by_pair, existing_by_student, seen_offerings)
        if group_present:
            ev.issues.append(_Issue("Group", "A Group column was present and ignored — Group is derived from the intake.", "NOTE"))
        _persist_eval(row, ev)
        if (ev.offering_id or ev.unverified) and ev.student_id and ev.row_status == READY:
            seen_offerings[(ev.student_id, ev.offering_id or 0)] = row.id


# ---------------------------------------------------------------------------
# Review
# ---------------------------------------------------------------------------


def _load_batch(session: Session, batch_id: int) -> ImportBatch:
    batch = session.get(ImportBatch, batch_id)
    if batch is None:
        raise StudentImportError("That import batch was not found.")
    return batch


_STATUS_LABELS = {
    READY: "Ready",
    NEEDS_CORRECTION: "Needs correction",
    DUPLICATE: "Duplicate",
    UNMATCHED_REFERENCE: "Unmatched reference",
    EXCLUDED: "Excluded by user",
}


def review_dict(session: Session, batch: ImportBatch) -> dict:
    rows = list(
        session.execute(
            select(ImportStagedRow)
            .where(ImportStagedRow.import_batch_id == batch.id)
            .order_by(ImportStagedRow.source_row_number)
        ).scalars()
    )
    counts = {label: 0 for label in _STATUS_LABELS.values()}
    blocking = 0
    for row in rows:
        counts[_STATUS_LABELS.get(row.status, row.status)] += 1
        if row.status in {NEEDS_CORRECTION, UNMATCHED_REFERENCE, DUPLICATE}:
            blocking += 1

    duplicates = _duplicate_contexts(session, rows)
    duration_options = _duration_options(session, rows)
    blocking_reasons: list[str] = []
    if blocking:
        blocking_reasons.append(f"{blocking} row(s) need a decision or correction before Confirm.")

    return {
        "batch_id": batch.id,
        "batch_reference": batch.batch_reference,
        "file_name": batch.file_name,
        "status": batch.status,
        "training_context": None,
        "rows_read": batch.row_count,
        "counts": counts,
        "can_apply": batch.status == "STAGED" and blocking == 0,
        "blocking_reasons": blocking_reasons,
        "rows": [_row_dict(row) for row in rows],
        "duplicates": [d for d in duplicates],
        "duration_options": duration_options,
    }


def _duration_options(session: Session, rows: list[ImportStagedRow]) -> dict[str, list[int]]:
    """The rolling-timetable durations each qualification in this file offers.

    A TBD row is resolved by choosing one of these, so the review can present a
    real choice instead of asking the user to guess. One query for the batch.
    """
    codes = {(row.qualification_value or "").strip().upper() for row in rows}
    codes.discard("")
    if not codes:
        return {}
    found = session.execute(
        select(RollingTimetableWeek.qualification_code, RollingTimetableWeek.duration_weeks)
        .where(func.upper(RollingTimetableWeek.qualification_code).in_(codes))
        .distinct()
    ).all()
    options: dict[str, set[int]] = {}
    for code, duration in found:
        options.setdefault(code.upper(), set()).add(duration)
    return {code: sorted(values) for code, values in options.items()}


def _row_dict(row: ImportStagedRow) -> dict:
    return {
        "id": row.id,
        "source_row_number": row.source_row_number,
        "status": row.status,
        "student_id_value": row.student_id_value,
        "first_name_value": row.first_name_value,
        "last_name_value": row.last_name_value,
        "college_value": row.college_value,
        "campus_value": row.campus_value,
        "qualification_value": row.qualification_value,
        "coe_status_value": row.coe_status_value,
        "ct_student_value": row.ct_student_value,
        "status_value": row.status_value,
        "proposed_start_date_value": row.proposed_start_date_value,
        "proposed_end_date_value": row.proposed_end_date_value,
        "personal_email_value": row.personal_email_value,
        "primary_phone_value": row.primary_phone_value,
        "resolved_college_id": row.resolved_college_id,
        "resolved_campus_id": row.resolved_campus_id,
        "resolved_qualification_id": row.resolved_qualification_id,
        "resolved_offering_id": row.resolved_offering_id,
        "derived_intake_label": row.derived_intake_label,
        "derived_group_code": row.derived_group_code,
        "intake_match_status": row.intake_match_status,
        "duration_override_weeks": row.duration_override_weeks,
        "duplicate_scope": row.duplicate_scope,
        "existing_student_id": row.existing_student_id,
        "duplicate_decision": row.duplicate_decision,
        "existing_status_value": row.existing_status_value,
        "college_choice": row.college_choice,
        "campus_choice": row.campus_choice,
        "qualification_choice": row.qualification_choice,
        "issues": [
            {"field_name": i.field_name, "message": i.message, "issue_status": i.issue_status}
            for i in row.issues
        ],
    }


def _duplicate_contexts(session: Session, rows: list[ImportStagedRow]) -> list[dict]:
    contexts: list[dict] = []
    for row in rows:
        if not row.duplicate_scope or row.existing_student_id is None:
            continue
        stored = session.get(Student, row.existing_student_id)
        if stored is None:
            continue
        stored_read = student_service.get_student(session, stored.id)
        fields = [
            ("first_name", stored.first_name, row.first_name_value),
            ("last_name", stored.last_name, row.last_name_value),
            ("coe_status", stored.coe_status, (row.coe_status_value or "").strip()),
            ("proposed_start_date", stored.proposed_start_date.isoformat(), row.proposed_start_date_value),
            ("proposed_end_date", stored.proposed_end_date.isoformat(), row.proposed_end_date_value),
            ("status", stored.status, (row.status_value or "").strip()),
        ]
        contexts.append(
            {
                "staged_row_id": row.id,
                "scope": row.duplicate_scope,
                "existing_student_id": stored.id,
                "existing_status": stored.status,
                "existing_qualification_code": stored_read["qualification_code"],
                "incoming_qualification_code": (row.qualification_value or "").strip(),
                "fields": [
                    {"field": name, "stored": _s(s), "incoming": _s(i), "differs": _s(s) != _s(i)}
                    for name, s, i in fields
                ],
            }
        )
    return contexts


def _s(value) -> str:
    return "" if value is None else str(value)


# ---------------------------------------------------------------------------
# Patch (corrections, exclusions, decisions)
# ---------------------------------------------------------------------------


def patch_rows(session: Session, batch: ImportBatch, items: list) -> None:
    if batch.status != "STAGED":
        raise StudentImportError("This batch has already been applied or abandoned.")
    by_id = {
        r.id: r
        for r in session.execute(
            select(ImportStagedRow).where(ImportStagedRow.import_batch_id == batch.id)
        ).scalars()
    }
    for item in items:
        row = by_id.get(item.row_id)
        if row is None:
            continue
        if item.corrections:
            _apply_corrections(row, item.corrections)
        if item.exclude is not None:
            row.excluded_by_user = bool(item.exclude)
        if item.accept_exception is not None:
            # True accepts the row's broken rule for this import; False is Undo.
            row.working_values = {**(row.working_values or {}), "_accepted_exception": bool(item.accept_exception)}
        if item.duplicate_decision is not None:
            row.duplicate_decision = item.duplicate_decision.upper()
        if item.duration_weeks is not None:
            # 0 or a negative value clears the choice and returns the row to the
            # duration its dates imply.
            row.duration_override_weeks = item.duration_weeks if item.duration_weeks > 0 else None
        if item.status_value is not None:
            row.status_value = item.status_value.strip() or None
        if item.existing_status_value is not None:
            row.existing_status_value = item.existing_status_value.strip() or None
        if item.reference_entity and item.reference_choice:
            entity = item.reference_entity.strip().lower()
            if entity in {"college", "campus", "qualification"}:
                setattr(row, f"{entity}_choice", item.reference_choice.strip().upper())
                if item.reference_choice.strip().upper() == "RESOLVE" and item.reference_resolved_id:
                    setattr(row, f"resolved_{entity}_id", item.reference_resolved_id)
                else:
                    setattr(row, f"resolved_{entity}_id", None)
    session.flush()

    # Re-validate the whole batch: bounded, and keeps every derived value current.
    staged = list(by_id.values())
    lookups = _load_lookups(session)
    _evaluate_batch(session, staged, lookups)
    session.flush()


_CORRECTION_COLUMNS = {
    C_STUDENT_ID: "student_id_value",
    C_FIRST: "first_name_value",
    C_LAST: "last_name_value",
    C_COLLEGE: "college_value",
    C_CAMPUS: "campus_value",
    C_QUAL: "qualification_value",
    C_COE: "coe_status_value",
    C_CT: "ct_student_value",
    C_START: "proposed_start_date_value",
    C_END: "proposed_end_date_value",
    C_PERSONAL_EMAIL: "personal_email_value",
    C_PHONE: "primary_phone_value",
    C_STATUS: "status_value",
}


def _apply_corrections(row: ImportStagedRow, corrections) -> None:
    for correction in corrections:
        attr = _CORRECTION_COLUMNS.get(correction.column)
        if attr is None:
            continue
        setattr(row, attr, (correction.value or "").strip() or None)
        # A corrected reference clears its earlier RESOLVE binding.
        if correction.column in {C_COLLEGE, C_CAMPUS, C_QUAL}:
            entity = {C_COLLEGE: "college", C_CAMPUS: "campus", C_QUAL: "qualification"}[correction.column]
            setattr(row, f"resolved_{entity}_id", None)
            setattr(row, f"{entity}_choice", None)
    row.corrected = True


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def apply_batch(session: Session, batch: ImportBatch, user: User) -> dict:
    if batch.status != "STAGED":
        raise StudentImportError("This batch has already been applied or abandoned.")
    rows = list(
        session.execute(
            select(ImportStagedRow).where(ImportStagedRow.import_batch_id == batch.id)
        ).scalars()
    )
    blocking = [r for r in rows if r.status in {NEEDS_CORRECTION, UNMATCHED_REFERENCE, DUPLICATE}]
    if blocking:
        raise StudentImportError(
            f"{len(blocking)} row(s) still need a decision or correction. Nothing was written."
        )

    lookups = _load_lookups(session)
    writable = [r for r in rows if r.status == READY]

    # 1) Raise suggestions for RAISE choices (rule 2.4), deduplicated by value.
    suggestions_raised = _raise_suggestions(session, rows, user)

    # 2) Resolve every needed group in ONE query, then create the missing ones,
    #    so students in one intake share a single group row (A11).
    group_ids, groups_created = _resolve_groups(session, writable)

    # 2b) Approved Course Duration Options for any user-chosen duration (OD-08).
    duration_option_ids = _resolve_duration_options(session, writable)

    # 3) Updates for duplicate decisions (few, not per-student).
    updated = 0
    inserts: list[dict] = []
    for row in writable:
        if row.duplicate_scope == "SAME_QUALIFICATION" and row.duplicate_decision == "KEEP_INCOMING" and row.existing_student_id:
            _update_existing(session, row, lookups, group_ids, duration_option_ids)
            updated += 1
            continue
        if row.duplicate_scope == "DIFFERENT_QUALIFICATION" and row.existing_status_value and row.existing_student_id:
            existing = session.get(Student, row.existing_student_id)
            if existing is not None:
                existing.status = row.existing_status_value.upper().replace(" ", "_")
        inserts.append(_insert_dict(row, lookups, group_ids, duration_option_ids))

    # 4) One multi-row insert for the new students (rule 2.9, check E4).
    inserted = 0
    if inserts:
        session.execute(insert(Student), inserts)
        inserted = len(inserts)

    excluded = sum(1 for r in rows if r.status == EXCLUDED)
    matched = sum(1 for r in writable if r.intake_match_status == "MATCHED")
    tbd = sum(1 for r in writable if r.intake_match_status == "TBD")
    na = sum(1 for r in writable if r.intake_match_status == "NOT_APPLICABLE")

    now = dt.datetime.now(dt.timezone.utc)
    batch.status = "APPLIED"
    batch.completed_at = now
    batch.inserted_count = inserted
    batch.excluded_count = excluded
    batch.duplicate_count = sum(1 for r in rows if r.duplicate_scope)
    batch.unmatched_count = tbd
    # The staged copy of the file has done its work. It is reachable from
    # nowhere once the import finishes, and holds names, emails and phone
    # numbers, so it is dropped here rather than kept for nothing (21 September
    # 2026). The batch row stays as the record of the upload and its counts.
    session.execute(delete(ImportStagedRow).where(ImportStagedRow.import_batch_id == batch.id))
    session.flush()

    record_activity(
        session,
        user=user,
        action="IMPORT",
        page_or_function=STUDENT_IMPORT_PAGE,
        detail=(
            f"Imported {batch.file_name}: {inserted} inserted, {updated} updated, "
            f"{excluded} excluded from {batch.row_count} rows."
        ),
        record_reference=batch.batch_reference,
        result="COMPLETED",
    )
    return {
        "batch_id": batch.id,
        "rows_read": batch.row_count,
        "inserted": inserted,
        "updated": updated,
        "excluded": excluded,
        "duplicates": batch.duplicate_count or 0,
        "unmatched": tbd,
        "suggestions_raised": suggestions_raised,
        # Written with no offering because a reference was raised (15 September 2026).
        "unverified": sum(1 for r in writable if not r.resolved_offering_id),
        "intakes_matched": matched,
        "intakes_tbd": tbd,
        "intakes_not_applicable": na,
        "groups_created": groups_created,
    }


def _resolve_duration_options(
    session: Session, writable: list[ImportStagedRow]
) -> dict[tuple[int, int], int]:
    """Map (offering, duration weeks) to an approved `offering_duration_options` id.

    Only rows where the user chose a duration need one. A duration with no
    approved option for that offering simply stores no Course Duration Option —
    the FK guarantees a student can never carry one that is not approved for
    their own offering.
    """
    wanted = {
        (row.resolved_offering_id, row.duration_override_weeks)
        for row in writable
        if row.duration_override_weeks and row.resolved_offering_id
    }
    if not wanted:
        return {}
    found = session.execute(
        select(OfferingDurationOption).where(
            tuple_(
                OfferingDurationOption.course_offering_id, OfferingDurationOption.duration_weeks
            ).in_(list(wanted))
        )
    ).scalars()
    return {(option.course_offering_id, option.duration_weeks): option.id for option in found}


def _resolve_groups(
    session: Session, writable: list[ImportStagedRow]
) -> tuple[dict[tuple[int, str], int], int]:
    """Map each matched (offering, intake label) to a group row, creating misses.

    One query resolves the existing groups; only genuinely new intakes are
    inserted. Two students in the same intake therefore share one row (A11).
    """
    needed: dict[tuple[int, str], tuple[str, dt.date]] = {}
    for row in writable:
        if row.intake_match_status == "MATCHED" and row.resolved_offering_id and row.derived_intake_label:
            key = (row.resolved_offering_id, row.derived_intake_label)
            needed[key] = (row.derived_group_code or "N/A", _intake_date_from_label(row.derived_intake_label))

    group_ids: dict[tuple[int, str], int] = {}
    if not needed:
        return group_ids, 0

    existing = session.execute(
        select(StudentGroup).where(
            tuple_(StudentGroup.course_offering_id, StudentGroup.rolling_intake_label).in_(list(needed.keys()))
        )
    ).scalars()
    for group in existing:
        group_ids[(group.course_offering_id, group.rolling_intake_label)] = group.id

    created = 0
    for key, (group_code, intake_date) in needed.items():
        if key in group_ids:
            continue
        group = StudentGroup(
            group_code=group_code,
            course_offering_id=key[0],
            intake=intake_date,
            rolling_intake_label=key[1],
            is_active=True,
        )
        session.add(group)
        session.flush()
        group_ids[key] = group.id
        created += 1
    return group_ids, created


def _intake_date_from_label(label: str) -> dt.date:
    """Read the date component from `Code_Duration_DD Mon YYYY_Group_Intake`."""
    parts = label.split("_")
    if len(parts) >= 3:
        try:
            return dt.datetime.strptime(parts[2], "%d %b %Y").date()
        except ValueError:
            pass
    return dt.date.today()


def _insert_dict(
    row: ImportStagedRow,
    lookups: Lookups,
    group_ids: dict[tuple[int, str], int],
    duration_option_ids: dict[tuple[int, int], int] | None = None,
) -> dict:
    start, _ = parse_day_first_date(row.proposed_start_date_value)
    end, _ = parse_day_first_date(row.proposed_end_date_value)
    college = lookups.college_by_id.get(row.resolved_college_id)
    email = student_service.derive_college_email(row.student_id_value or "", college) if college else ""
    ct = (row.ct_student_value or "").strip().lower() in _CT_TRUE
    status = (row.status_value or "ACTIVE").strip().upper().replace(" ", "_") or "ACTIVE"
    group_id = None
    if row.intake_match_status == "MATCHED" and row.resolved_offering_id and row.derived_intake_label:
        group_id = group_ids.get((row.resolved_offering_id, row.derived_intake_label))
    return {
        "student_id": (row.student_id_value or "").strip(),
        "first_name": (row.first_name_value or "").strip(),
        "last_name": (row.last_name_value or "").strip() or None,
        "coe_status": _COE_VALUES.get((row.coe_status_value or "").strip().lower(), "NON_COE"),
        "ct_student": ct,
        "status": status,
        "intake_match_status": row.intake_match_status or "TBD",
        "proposed_start_date": start,
        "proposed_end_date": end,
        "personal_email": (row.personal_email_value or "").strip() or None,
        "primary_phone": (row.primary_phone_value or "").strip() or None,
        "college_email": email,
        "course_offering_id": row.resolved_offering_id,
        # What the file said, kept whether or not it resolved: the evidence a
        # suggestion is raised from, and what a later resolve matches on.
        "college_text": (row.college_value or "").strip() or None,
        "campus_text": (row.campus_value or "").strip() or None,
        "qualification_text": (row.qualification_value or "").strip() or None,
        "student_group_id": group_id,
        # A Credit Transfer student never carries a Course Duration Option
        # (approved 13 August 2026); everyone else carries the one the user
        # chose, when an approved option exists for their offering.
        "course_duration_option_id": (
            None
            if ct
            else (duration_option_ids or {}).get((row.resolved_offering_id, row.duration_override_weeks))
        ),
    }


def _update_existing(
    session: Session,
    row: ImportStagedRow,
    lookups: Lookups,
    group_ids: dict[tuple[int, str], int],
    duration_option_ids: dict[tuple[int, int], int] | None = None,
) -> None:
    """Keep-incoming: replace the stored record field for field (rule 2.6 D4)."""
    student = session.get(Student, row.existing_student_id)
    if student is None:
        return
    for attr, value in _insert_dict(row, lookups, group_ids, duration_option_ids).items():
        setattr(student, attr, value)
    session.flush()


def _student_attributes(entity: str, row: ImportStagedRow) -> dict:
    """What the Add form can be pre-filled with from a student row (15 September 2026)."""
    college = (row.college_value or "").strip()
    campus = (row.campus_value or "").strip()
    if entity == "COLLEGE":
        return {"campuses": [campus] if campus else []}
    if entity == "CAMPUS":
        return {"college": college}
    location = {key: value for key, value in (("college", college), ("campus", campus)) if value}
    return {"locations": [location] if location else []}


def _raise_suggestions(session: Session, rows: list[ImportStagedRow], user: User) -> int:
    """Write reference_suggestion rows for RAISE choices, deduplicated (R3, R6)."""
    raised = 0
    for row in rows:
        for entity, value in (
            ("COLLEGE", row.college_value),
            ("CAMPUS", row.campus_value),
            ("QUALIFICATION", row.qualification_value),
        ):
            choice = getattr(row, f"{entity.lower()}_choice", None)
            if choice == "RAISE" and value:
                # One entry per unmatched value, whose occurrence_count rises
                # (R6) - not one per student. A campus is the exception: the
                # same spelling is a different place at a different college
                # ("Sydney (Haymarket)" is not one campus), so a campus entry
                # names its college and is decided per college (21 September 2026).
                context = {"college": (row.college_value or "").strip()} if entity == "CAMPUS" else {}
                created = raise_reference_suggestion(
                    session,
                    entity_type=entity,
                    raw_value=value,
                    context={key: value for key, value in context.items() if value},
                    source="STUDENT_IMPORT",
                    attributes=_student_attributes(entity, row),
                )
                raised += 1 if created else 0
    return raised


def abandon_batch(session: Session, batch: ImportBatch) -> None:
    if batch.status != "STAGED":
        raise StudentImportError("Only a staged batch can be abandoned.")
    session.execute(delete(ImportBatch).where(ImportBatch.id == batch.id))
    session.flush()
