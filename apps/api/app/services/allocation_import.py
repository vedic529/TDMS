"""Parse, validate and apply allocation workbooks. Web and CLI share this module."""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.models.allocation import (
    AllocationDelivery,
    AllocationDeliveryIntake,
    AllocationImportBatch,
    AllocationSession,
    AllocationSourceRow,
    ReferenceSuggestion,
)
from app.models.college import Campus, College, CollegeCampus
from app.models.facility import Facility, FacilityCollege
from app.models.qualification import Qualification, Unit
from app.models.timetable import RollingTimetableWeek
from app.models.trainer import Trainer
from app.models.user import User
from app.services.activity import record_activity
from app.services.allocation_profiles import OPTIONAL_COLUMNS, REQUIRED_COLUMNS, profile_for
from app.services import allocation_rules as rules

KIND_MISSING_HEADER = "missing_or_unknown_header"
KIND_REQUIRED_EMPTY = "required_empty"
KIND_BAD_DATE = "unreadable_or_ambiguous_date"
KIND_BAD_TIME = "unparseable_days_and_times"
KIND_WEEKDAY = "weekday_not_allowed"
KIND_BAD_ENUM = "unapproved_enum"
KIND_PRACTICAL_VIRTUAL = "practical_cannot_be_virtual"
KIND_F2FV_PRACTICAL = "f2fv_with_practical"
KIND_MODE_CONTRADICTION = "mode_contradicts_classrooms"
KIND_DAY_MISMATCH = "classroom_or_trainer_day_without_class"
KIND_KEY_CONFLICT = "business_key_conflict"
KIND_DATE_ORDER = "end_before_start"
KIND_NAME_MISMATCH = "name_disagrees_with_id"
KIND_UNRESOLVED = "unresolved_reference"
KIND_NO_INTAKE = "no_rolling_intake"
KIND_TEACHING_DAYS = "not_two_teaching_days"
KIND_CLASS_LENGTH = "not_eight_hours"
KIND_CAPACITY = "capacity_mismatch"

TIME_LINE_RE = re.compile(
    r"^(?P<day>[A-Za-z]+)\s*-\s*(?P<sh>\d{1,2})(?::(?P<sm>\d{2}))?\s*(?P<sp>am|pm)\s+to\s+"
    r"(?P<eh>\d{1,2})(?::(?P<em>\d{2}))?\s*(?P<ep>am|pm)\s*$",
    re.IGNORECASE,
)
NAMED_VALUE_RE = re.compile(r"^(?P<day>[A-Za-z]+)\s*-\s*(?P<value>.+)$")
AMBIGUOUS_DATE_RE = re.compile(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}$")


class AllocationImportError(ValueError):
    pass


@dataclass
class Discrepancy:
    kind: str
    severity: str
    row_number: int | None
    column: str | None
    value: str | None
    message: str
    edit_fields: list[dict] = field(default_factory=list)


def issue_id(item: Discrepancy) -> str:
    return "|".join([item.kind, str(item.row_number or ""), item.column or "", item.value or ""])


@dataclass
class ImportOverrides:
    corrections: list[dict]
    except_ids: set[str]
    raise_ids: set[str]
    no_raise_ids: set[str]
    raise_all_unresolved: bool = True

    @classmethod
    def from_payload(cls, payload: object, raise_all_unresolved: bool = True) -> "ImportOverrides":
        data = payload if isinstance(payload, dict) else {}
        return cls(
            corrections=list(data.get("corrections") or []),
            except_ids=set(data.get("except_ids") or []),
            raise_ids=set(data.get("raise_ids") or []),
            no_raise_ids=set(data.get("no_raise_ids") or []),
            raise_all_unresolved=raise_all_unresolved,
        )

    def excepted_headers(self) -> set[str]:
        names: set[str] = set()
        for raw in self.except_ids:
            kind, _row, column, value = (raw.split("|", 3) + ["", "", ""])[:4]
            if kind == KIND_MISSING_HEADER:
                names.add(column or value)
        return {name for name in names if name}

    def should_raise(self, item: Discrepancy) -> bool:
        key = issue_id(item)
        if key in self.except_ids or key in self.no_raise_ids:
            return False
        if key in self.raise_ids:
            return True
        return self.raise_all_unresolved

    def is_excepted(self, item: Discrepancy) -> bool:
        return issue_id(item) in self.except_ids


@dataclass
class PlannedSession:
    stream: str
    weekday: str
    start_time: dt.time
    end_time: dt.time
    delivery_mode: str
    facility_id: int | None
    virtual_kind: str | None
    classroom_text: str | None
    trainer_id: int | None
    trainer_text: str | None


@dataclass
class PlannedDelivery:
    source_row: int
    training_package: str
    college_id: int | None
    campus_id: int | None
    qualification_id: int | None
    qualification_code: str
    duration_weeks: int
    group_code: str
    unit_id: int | None
    unit_code: str
    uoc_type: str
    mode_of_delivery: str
    start_date: dt.date
    end_date: dt.date
    classroom_size: int | None
    remarks: str | None
    sessions: list[PlannedSession]
    intake_labels: list[tuple[str, str]]
    intake_match_status: str
    raw_values: dict[str, str]
    refused: bool = False
    needs_correction: bool = False
    #: The College and Campus exactly as the file spelled them. Stored on the
    #: delivery whenever the identifier could not be resolved, so the row can be
    #: found and repaired when the value is later approved (section 2.3).
    college_value: str = ""
    campus_value: str = ""


@dataclass
class ImportReview:
    status: str
    training_package: str
    file_name: str
    rows_read: int
    deliveries_that_would_be_written: int
    sessions_that_would_be_written: int
    qualifications: list[str]
    units: list[str]
    intakes_matched: int
    intakes_not_matched: int
    suggestions_that_would_be_raised: int
    discrepancies: list[Discrepancy]
    refused: bool
    can_apply: bool
    raise_suggestions: bool = True
    existing_deliveries: int = 0


def _clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    return str(value).strip()


def _is_null(value: str) -> bool:
    return value == "" or value.upper() == "NA"


def normalise_suggestion_value(raw: str) -> str:
    return " ".join(raw.upper().split())


def _context_key(context: dict) -> str:
    return json.dumps(context, sort_keys=True)


def _is_ignored_extra_header(name: str) -> bool:
    compact = " ".join(name.lower().split())
    return compact in {
        "mscris class size",
        "mscris classroom size",
        "mscris class capacity",
        "mscris classroom capacity",
    }


def _unresolved_severity(raise_suggestions: bool) -> str:
    return "warn" if raise_suggestions else "refuse"


ROW_SKIP_KINDS = {
    KIND_REQUIRED_EMPTY,
    KIND_BAD_DATE,
    KIND_BAD_TIME,
    KIND_WEEKDAY,
    KIND_BAD_ENUM,
    KIND_PRACTICAL_VIRTUAL,
    KIND_F2FV_PRACTICAL,
    KIND_MODE_CONTRADICTION,
    KIND_DAY_MISMATCH,
    KIND_KEY_CONFLICT,
    KIND_DATE_ORDER,
}


def _emit_unresolved(
    issues: list[Discrepancy],
    suggestions: dict,
    overrides: ImportOverrides,
    *,
    entity_type: str,
    row_number: int,
    column: str,
    value: str,
    message: str,
    context: dict,
) -> None:
    item = Discrepancy(KIND_UNRESOLVED, "refuse", row_number, column, value, message)
    if overrides.is_excepted(item):
        item.severity = "warn"
        item.message = f"{message} Accepted as an exception — stored without an approved match."
        # Collected here, written at apply time: an abandoned review must leave
        # nothing behind (section 2.9.1).
        _raise_or_count_suggestion(suggestions, entity_type, value, context, kind="EXCEPT")
    elif overrides.should_raise(item):
        item.severity = "warn"
        _raise_or_count_suggestion(suggestions, entity_type, value, context)
    else:
        item.message = f"{message} Edit the value, raise a suggestion, or accept it as an exception."
    if any(issue_id(existing) == issue_id(item) for existing in issues):
        return
    issues.append(item)


def _has_classroom_values(profile, values: dict[str, str]) -> bool:
    if not _is_null(values.get("Theory Classroom Name", "")):
        return True
    return bool(profile.has_practical) and not _is_null(values.get("Practical Classroom Name", ""))


def _edit_fields(values: dict[str, str], *columns: str) -> list[dict]:
    """Both sides of a disagreement — the user may correct either value."""
    fields: list[dict] = []
    seen: set[str] = set()
    for column in columns:
        if not column or column in seen:
            continue
        seen.add(column)
        fields.append({"column": column, "value": values.get(column, "")})
    return fields


def _mode_classroom_edit_fields(profile, values: dict[str, str]) -> list[dict]:
    columns = ["Mode of Delivery", "Theory Classroom Name"]
    practical = values.get("Practical Classroom Name", "")
    if profile.has_practical or not _is_null(practical):
        columns.append("Practical Classroom Name")
    return _edit_fields(values, *columns)


def _apply_corrections(rows: list[list], columns: dict[str, int], corrections: list[dict]) -> None:
    for entry in corrections:
        try:
            row_number = int(entry.get("row_number"))
            column = str(entry.get("column") or "")
        except (TypeError, ValueError):
            continue
        index = columns.get(column)
        row_index = row_number - 2
        if index is None or row_index < 0 or row_index >= len(rows):
            continue
        while len(rows[row_index]) <= index:
            rows[row_index].append("")
        rows[row_index][index] = entry.get("value") or ""


def _hour(hour: int, minute: int, meridian: str) -> dt.time:
    hour = hour % 12
    if meridian.lower() == "pm":
        hour += 12
    return dt.time(hour, minute)


def parse_days_and_times(text: str, row_number: int, column: str, issues: list[Discrepancy]) -> list[tuple[str, dt.time, dt.time]]:
    if _is_null(text):
        return []
    parsed: list[tuple[str, dt.time, dt.time]] = []
    for raw_line in re.split(r"[\r\n]+", text):
        line = raw_line.strip()
        if not line:
            continue
        match = TIME_LINE_RE.match(line)
        if not match:
            issues.append(
                Discrepancy(
                    KIND_BAD_TIME,
                    "refuse",
                    row_number,
                    column,
                    line,
                    f"{column} could not be read: {line}",
                )
            )
            continue
        day = rules.WEEKDAY_NAMES.get(match.group("day").upper())
        if not day:
            issues.append(
                Discrepancy(KIND_WEEKDAY, "refuse", row_number, column, line, f"{line} is not an allowed weekday.")
            )
            continue
        start = _hour(int(match.group("sh")), int(match.group("sm") or 0), match.group("sp"))
        end = _hour(int(match.group("eh")), int(match.group("em") or 0), match.group("ep"))
        if end <= start:
            issues.append(Discrepancy(KIND_BAD_TIME, "refuse", row_number, column, line, f"{line} ends before it starts."))
            continue
        parsed.append((day, start, end))
    return parsed


def parse_named_or_shared(text: str, days: list[str], row_number: int, column: str, issues: list[Discrepancy]) -> dict[str, str]:
    if _is_null(text):
        return {}
    lines = [line.strip() for line in re.split(r"[\r\n]+", text) if line.strip()]
    if len(lines) == 1 and not NAMED_VALUE_RE.match(lines[0]):
        return {day: lines[0] for day in days}
    mapped: dict[str, str] = {}
    for line in lines:
        match = NAMED_VALUE_RE.match(line)
        if not match:
            issues.append(
                Discrepancy(KIND_DAY_MISMATCH, "refuse", row_number, column, line, f"{column} is not a day-prefixed value: {line}")
            )
            continue
        day = rules.WEEKDAY_NAMES.get(match.group("day").upper())
        if day not in days:
            issues.append(
                Discrepancy(
                    KIND_DAY_MISMATCH,
                    "refuse",
                    row_number,
                    column,
                    line,
                    f"{column} names {match.group('day')} which has no matching class day.",
                )
            )
            continue
        mapped[day] = match.group("value").strip()
    return mapped


def parse_date(value: object, row_number: int, column: str, issues: list[Discrepancy]) -> dt.date | None:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = _clean(value)
    if _is_null(text):
        return None
    if AMBIGUOUS_DATE_RE.match(text):
        issues.append(
            Discrepancy(
                KIND_BAD_DATE,
                "refuse",
                row_number,
                column,
                text,
                f"{column} is ambiguous. Use ISO (YYYY-MM-DD) or d-mmm-yy.",
            )
        )
        return None
    for fmt in ("%Y-%m-%d", "%d-%b-%y", "%d-%b-%Y", "%d %b %Y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    issues.append(Discrepancy(KIND_BAD_DATE, "refuse", row_number, column, text, f"{column} cannot be read as a date."))
    return None


def _read_tabular(file_name: str, payload: bytes) -> tuple[list[str], list[list[object]]]:
    lower = file_name.lower()
    if lower.endswith(".csv"):
        rows = list(csv.reader(io.StringIO(payload.decode("utf-8-sig"))))
        if not rows:
            return [], []
        return [_clean(cell) for cell in rows[0]], [list(row) for row in rows[1:]]
    if lower.endswith(".xlsx"):
        import openpyxl

        workbook = openpyxl.load_workbook(io.BytesIO(payload), data_only=True, read_only=True)
        try:
            values = list(workbook.worksheets[0].iter_rows(values_only=True))
        finally:
            workbook.close()
        if not values:
            return [], []
        return [_clean(cell) for cell in values[0]], [list(row) for row in values[1:]]
    raise AllocationImportError("The file must be a CSV or XLSX workbook.")


def _map_headers(
    headers: list[str], issues: list[Discrepancy], excepted_headers: set[str] | None = None
) -> dict[str, int] | None:
    known = set(REQUIRED_COLUMNS) | set(OPTIONAL_COLUMNS)
    ignored = excepted_headers or set()
    index: dict[str, int] = {}
    unknown: list[str] = []
    for i, header in enumerate(headers):
        name = " ".join(header.split())
        if not name:
            continue
        if _is_ignored_extra_header(name) or name in ignored:
            continue
        if name not in known:
            unknown.append(name)
            continue
        index.setdefault(name, i)
    blocking_unknown: list[str] = []
    for name in unknown:
        item = Discrepancy(
            KIND_MISSING_HEADER,
            "refuse",
            1,
            name,
            name,
            f"Column '{name}' is not in the allocation schema. Remove it, or accept it as an exception to ignore it.",
        )
        issues.append(item)
    if unknown:
        return None
    missing = [name for name in REQUIRED_COLUMNS if name not in index]
    if missing:
        issues.append(
            Discrepancy(
                KIND_MISSING_HEADER,
                "refuse",
                1,
                None,
                ", ".join(missing),
                "Missing required column(s): " + ", ".join(missing) + ".",
            )
        )
        return None
    return index


def _cell(row: list[object], columns: dict[str, int], name: str) -> object:
    if name not in columns:
        return ""
    index = columns[name]
    return row[index] if index < len(row) else ""


def _lookups(session: Session) -> dict:
    colleges = {row.college_full_name.strip().upper(): row.id for row in session.execute(select(College)).scalars()}
    colleges.update({row.college_short_name.strip().upper(): row.id for row in session.execute(select(College)).scalars()})
    campuses = list(session.execute(select(Campus)).scalars())
    campus_by_location = {row.campus_location.strip().upper(): row.id for row in campuses}
    campus_by_name = {row.campus_name.strip().upper(): row.id for row in campuses}
    quals = { (row.qualification_code or "").upper(): row for row in session.execute(select(Qualification)).scalars() if row.qualification_code }
    units = {row.unit_code.upper(): row for row in session.execute(select(Unit)).scalars()}
    active_trainers = list(
        session.execute(select(Trainer).where(Trainer.is_deleted.is_(False), Trainer.is_active.is_(True))).scalars()
    )
    trainers = {row.trainer_name.strip().upper(): row.id for row in active_trainers}
    for row in active_trainers:
        trainers.setdefault(row.trainer_id.strip().upper(), row.id)
    facilities = list(session.execute(select(Facility)).scalars())
    college_campus = {(link.college_id, link.campus_id) for link in session.execute(select(CollegeCampus)).scalars()}
    facility_colleges = {(link.facility_id, link.college_id) for link in session.execute(select(FacilityCollege)).scalars()}
    return {
        "colleges": colleges,
        "campus_by_location": campus_by_location,
        "campus_by_name": campus_by_name,
        "campuses": {row.id: row for row in campuses},
        "quals": quals,
        "units": units,
        "trainers": trainers,
        "facilities": facilities,
        "college_campus": college_campus,
        "facility_colleges": facility_colleges,
    }


def _resolve_facility(lookups: dict, college_id: int | None, campus_id: int | None, name: str) -> Facility | None:
    needle = name.strip().upper()
    for facility in lookups["facilities"]:
        if facility.facility_reference.strip().upper() != needle:
            continue
        if campus_id and facility.campus_id != campus_id:
            continue
        if college_id and (facility.id, college_id) not in lookups["facility_colleges"] and lookups["facility_colleges"]:
            # If the room has no college links, still accept campus match.
            if any(fid == facility.id for fid, _ in lookups["facility_colleges"]):
                continue
        return facility
    return None


def _raise_or_count_suggestion(
    suggestions: dict[tuple, dict], entity_type: str, raw: str, context: dict, kind: str = "RAISE"
) -> None:
    """Count an unmatched value once per distinct (entity, value, context).

    `kind` separates a raised suggestion from an accepted exception. Both are
    collected here and written at apply time, so the two share one deduplication
    key and a value can never be pending and excepted at the same time.
    """
    key = (entity_type, normalise_suggestion_value(raw), _context_key(context), kind)
    if key in suggestions:
        suggestions[key]["occurrence_count"] += 1
    else:
        suggestions[key] = {
            "entity_type": entity_type,
            "raw_value": raw,
            "normalised_value": key[1],
            "context": context,
            "context_key": key[2],
            "occurrence_count": 1,
            "kind": kind,
        }


def _entity_contexts(values: dict[str, str]) -> dict[str, dict]:
    """The scoping context for each entity type (rule 1.4, section 2.6).

    A problem is listed once, so the key must be what genuinely distinguishes
    two entries that would resolve to two *different* approved records:

    * a college name is scoped by nothing above it;
    * a campus name by its college — the same name may exist under two;
    * a qualification code is nationally unique;
    * a unit by its qualification;
    * a room name by its campus;
    * a trainer by its college, preserving the existing scoping.

    Keying on the whole row instead — which is what this replaced — made one
    campus misspelling across fifty units into fifty separate queue entries.
    """
    return {
        "COLLEGE": {},
        "CAMPUS": {"college": values["College"]},
        "QUALIFICATION": {},
        "UNIT": {"qualification": values["Qualification Id"]},
        "FACILITY": {"campus": values["Campus Location"]},
        "TRAINER": {"college": values["College"]},
    }


def _match_intakes(session: Session, planned: PlannedDelivery) -> None:
    if not planned.unit_code or not planned.qualification_code:
        planned.intake_match_status = "NOT_FOUND"
        planned.intake_labels = []
        return
    rows = session.execute(
        select(RollingTimetableWeek.intake_label, RollingTimetableWeek.intake_group)
        .where(
            # Case-insensitive, matching the student importer. Comparing exactly
            # let the two subsystems disagree about the same intake when a code
            # was stored in a different case.
            func.upper(RollingTimetableWeek.qualification_code)
            == planned.qualification_code.upper(),
            RollingTimetableWeek.duration_weeks == planned.duration_weeks,
            RollingTimetableWeek.unit_code == planned.unit_code,
            RollingTimetableWeek.week_start_date <= planned.end_date,
            RollingTimetableWeek.week_end_date >= planned.start_date,
        )
        .distinct()
    ).all()
    planned.intake_labels = [(label, group) for label, group in rows]
    planned.intake_match_status = "MATCHED" if planned.intake_labels else "NOT_FOUND"


def _build_sessions(
    *,
    profile,
    times: list[tuple[str, dt.time, dt.time]],
    classrooms: dict[str, str],
    trainers: dict[str, str],
    stream: str,
    lookups: dict,
    college_id: int | None,
    campus_id: int | None,
    row_number: int,
    classroom_column: str,
    issues: list[Discrepancy],
    suggestions: dict,
    context: dict,
    overrides: ImportOverrides,
) -> list[PlannedSession]:
    sessions: list[PlannedSession] = []
    for day, start, end in times:
        if day not in rules.allowed_weekdays(stream):
            issues.append(
                Discrepancy(KIND_WEEKDAY, "refuse", row_number, classroom_column, day, f"{stream} cannot run on {day}.")
            )
            continue
        room = classrooms.get(day, "")
        trainer = trainers.get(day, "")
        virtual_kind = rules.virtual_kind_for(room) if room else None
        if virtual_kind and not rules.stream_may_be_virtual(stream):
            issues.append(
                Discrepancy(
                    KIND_PRACTICAL_VIRTUAL,
                    "refuse",
                    row_number,
                    classroom_column,
                    room,
                    f"A virtual value in {classroom_column} is refused — practical is never virtual.",
                )
            )
            continue
        facility_id = None
        classroom_text = room or None
        if virtual_kind:
            mode = "VIRTUAL"
        elif room:
            mode = "PHYSICAL"
            facility = _resolve_facility(lookups, college_id, campus_id, room)
            if facility:
                facility_id = facility.id
            else:
                _emit_unresolved(
                    issues,
                    suggestions,
                    overrides,
                    entity_type="FACILITY",
                    row_number=row_number,
                    column=classroom_column,
                    value=room,
                    message=f"{room} is not an approved facility.",
                    context=context["FACILITY"],
                )
        else:
            mode = "VIRTUAL" if stream == "MSCRIS" else "PHYSICAL"
        trainer_id = None
        trainer_text = trainer or None
        if trainer:
            trainer_id = lookups["trainers"].get(trainer.strip().upper())
            if trainer_id is None and stream != "MSCRIS":
                _emit_unresolved(
                    issues,
                    suggestions,
                    overrides,
                    entity_type="TRAINER",
                    row_number=row_number,
                    column="Trainer",
                    value=trainer,
                    message=f"{trainer} is not an approved trainer.",
                    context=context["TRAINER"],
                )
            if stream == "MSCRIS":
                trainer_id = None
        if stream == "MSCRIS":
            mode = "VIRTUAL"
            facility_id = None
            virtual_kind = virtual_kind or "FACE_TO_FACE_VIRTUAL"
            day = rules.MSCRIS_WEEKDAY
        sessions.append(
            PlannedSession(
                stream=stream,
                weekday=day,
                start_time=start,
                end_time=end,
                delivery_mode=mode,
                facility_id=facility_id,
                virtual_kind=virtual_kind,
                classroom_text=classroom_text,
                trainer_id=trainer_id,
                trainer_text=trainer_text,
            )
        )
        if not rules.is_standard_class_length(start, end, stream):
            hours = int(rules.expected_class_length(stream).total_seconds() // 3600)
            issues.append(
                Discrepancy(
                    KIND_CLASS_LENGTH,
                    "warn",
                    row_number,
                    classroom_column,
                    f"{start}-{end}",
                    f"This class day is not {hours} hours.",
                )
            )
    return sessions


def validate_bytes(
    session: Session,
    *,
    training_package: str,
    file_name: str,
    payload: bytes,
    raise_suggestions: bool = True,
    overrides: ImportOverrides | None = None,
) -> tuple[ImportReview, list[PlannedDelivery], dict]:
    package = training_package.upper()
    profile = profile_for(package)
    if profile is None:
        raise AllocationImportError(f"{package} does not have an allocation format profile yet.")
    issues: list[Discrepancy] = []
    overrides = overrides or ImportOverrides.from_payload({}, raise_suggestions)
    overrides.raise_all_unresolved = raise_suggestions
    headers, rows = _read_tabular(file_name, payload)
    columns = _map_headers(headers, issues, overrides.excepted_headers())
    lookups = _lookups(session)
    suggestions: dict[tuple, dict] = {}
    planned: list[PlannedDelivery] = []
    existing_deliveries = session.execute(
        select(func.count()).select_from(AllocationDelivery).where(AllocationDelivery.training_package == package)
    ).scalar_one()
    if columns is None:
        review = _review(
            package, file_name, len(rows), [], issues, suggestions, raise_suggestions, existing_deliveries
        )
        return review, [], suggestions
    _apply_corrections(rows, columns, overrides.corrections)

    keys: dict[tuple, PlannedDelivery] = {}
    for offset, raw in enumerate(rows, start=2):
        if not any(_clean(cell) for cell in raw):
            continue
        values = {name: _clean(_cell(raw, columns, name)) for name in REQUIRED_COLUMNS + OPTIONAL_COLUMNS}
        # Blank or NA mode means this is not an allocation row (notes, spacers, unused units).
        if _is_null(values["Mode of Delivery"]):
            continue
        empty_required = [name for name in profile.required if _is_null(values[name])]
        for name in empty_required:
            issues.append(Discrepancy(KIND_REQUIRED_EMPTY, "refuse", offset, name, "", f"{name} is required."))
        start = parse_date(_cell(raw, columns, "Unit of Competency Start Date"), offset, "Unit of Competency Start Date", issues)
        end = parse_date(_cell(raw, columns, "Unit of Competency End Date"), offset, "Unit of Competency End Date", issues)
        if start and end and end < start:
            issues.append(Discrepancy(KIND_DATE_ORDER, "refuse", offset, "Unit of Competency End Date", values["Unit of Competency End Date"], "End date is before start date."))
        uoc_type = rules.UOC_TYPE_VALUES.get(values["UoC Type"].upper())
        if values["UoC Type"] and not uoc_type:
            issues.append(Discrepancy(KIND_BAD_ENUM, "refuse", offset, "UoC Type", values["UoC Type"], "UoC Type is not an approved value."))
        mode = rules.MODE_VALUES.get(values["Mode of Delivery"].upper())
        if values["Mode of Delivery"] and not mode:
            issues.append(Discrepancy(KIND_BAD_ENUM, "refuse", offset, "Mode of Delivery", values["Mode of Delivery"], "Mode of Delivery is not an approved value."))
        duration = None
        try:
            duration = int(values["Duration in Weeks"])
        except ValueError:
            issues.append(Discrepancy(KIND_REQUIRED_EMPTY, "refuse", offset, "Duration in Weeks", values["Duration in Weeks"], "Duration in Weeks must be a whole number."))
        classroom_size = None
        if not _is_null(values["Classroom Size"]):
            try:
                classroom_size = int(values["Classroom Size"])
            except ValueError:
                classroom_size = None
        college_id = lookups["colleges"].get(values["College"].upper())
        campus_id = lookups["campus_by_location"].get(values["Campus Location"].upper()) or lookups["campus_by_name"].get(values["Campus Location"].upper())
        qual = lookups["quals"].get(values["Qualification Id"].upper())
        unit = lookups["units"].get(values["Units of Competency ID"].upper())
        # One issue, listed once (rule 1.4). The context is what genuinely
        # *scopes* the entity, not the whole row: keying a campus by its unit
        # turned one misspelling across fifty rows into fifty queue entries.
        context = _entity_contexts(values)
        if values["College"] and college_id is None:
            _emit_unresolved(
                issues, suggestions, overrides,
                entity_type="COLLEGE", row_number=offset, column="College", value=values["College"],
                message="College is not an approved record.", context=context["COLLEGE"],
            )
        if values["Campus Location"] and campus_id is None:
            _emit_unresolved(
                issues, suggestions, overrides,
                entity_type="CAMPUS", row_number=offset, column="Campus Location", value=values["Campus Location"],
                message="Campus is not an approved record.", context=context["CAMPUS"],
            )
        if values["Qualification Id"] and qual is None:
            _emit_unresolved(
                issues, suggestions, overrides,
                entity_type="QUALIFICATION", row_number=offset, column="Qualification Id", value=values["Qualification Id"],
                message="Qualification is not an approved record.", context=context["QUALIFICATION"],
            )
        elif qual and values["Qualification Name"] and qual.qualification_title.strip().upper() != values["Qualification Name"].upper():
            issues.append(
                Discrepancy(
                    KIND_NAME_MISMATCH,
                    "refuse",
                    offset,
                    "Qualification Name",
                    values["Qualification Name"],
                    "Qualification Name disagrees with Qualification Id.",
                    edit_fields=_edit_fields(values, "Qualification Id", "Qualification Name"),
                )
            )
        if values["Units of Competency ID"] and unit is None:
            _emit_unresolved(
                issues, suggestions, overrides,
                entity_type="UNIT", row_number=offset, column="Units of Competency ID", value=values["Units of Competency ID"],
                message="Unit is not an approved record.", context=context["UNIT"],
            )
        elif unit and values["Units of Competency Title"] and unit.unit_title.strip().upper() != values["Units of Competency Title"].upper():
            issues.append(
                Discrepancy(
                    KIND_NAME_MISMATCH,
                    "refuse",
                    offset,
                    "Units of Competency Title",
                    values["Units of Competency Title"],
                    "Unit title disagrees with Unit ID.",
                    edit_fields=_edit_fields(values, "Units of Competency ID", "Units of Competency Title"),
                )
            )
        if qual and package != values["Qualification Id"][:3].upper():
            issues.append(Discrepancy(KIND_NAME_MISMATCH, "refuse", offset, "Qualification Id", values["Qualification Id"], "Qualification code does not match the selected training package."))

        theory_times = parse_days_and_times(values["Theory Class Days and Times"], offset, "Theory Class Days and Times", issues)
        theory_days = [item[0] for item in theory_times]
        theory_rooms = parse_named_or_shared(values["Theory Classroom Name"], theory_days, offset, "Theory Classroom Name", issues)
        theory_trainers = parse_named_or_shared(values["Theory Trainer"], theory_days, offset, "Theory Trainer", issues)
        practical_times: list[tuple[str, dt.time, dt.time]] = []
        if profile.has_practical:
            practical_times = parse_days_and_times(values["Practical Class Days and Times"], offset, "Practical Class Days and Times", issues)
        elif any(not _is_null(values[name]) for name in ("Practical Classroom Name", "Practical Class Days and Times", "Practical Trainers", "Practical Class Capacity")):
            # BSB R–U must be NA; extra values are ignored as absent practical, not an error.
            practical_times = []
        practical_days = [item[0] for item in practical_times]
        practical_rooms = parse_named_or_shared(values["Practical Classroom Name"], practical_days, offset, "Practical Classroom Name", issues) if profile.has_practical else {}
        practical_trainers = parse_named_or_shared(values["Practical Trainers"], practical_days, offset, "Practical Trainers", issues) if profile.has_practical else {}
        mscris_times = parse_days_and_times(values["MSCRIS Days and Times"], offset, "MSCRIS Days and Times", issues)
        mscris_days = [item[0] for item in mscris_times] or ([rules.MSCRIS_WEEKDAY] if not _is_null(values["MSCRIS Class Name"]) else [])
        mscris_rooms = parse_named_or_shared(values["MSCRIS Class Name"], mscris_days, offset, "MSCRIS Class Name", issues)
        mscris_trainers = parse_named_or_shared(values["MSCRIS Trainers"], mscris_days, offset, "MSCRIS Trainers", issues)

        sessions = _build_sessions(
            profile=profile,
            times=theory_times,
            classrooms=theory_rooms,
            trainers=theory_trainers,
            stream="THEORY",
            lookups=lookups,
            college_id=college_id,
            campus_id=campus_id,
            row_number=offset,
            classroom_column="Theory Classroom Name",
            issues=issues,
            suggestions=suggestions,
            context=context,
            overrides=overrides,
        )
        if profile.has_practical:
            sessions.extend(
                _build_sessions(
                    profile=profile,
                    times=practical_times,
                    classrooms=practical_rooms,
                    trainers=practical_trainers,
                    stream="PRACTICAL",
                    lookups=lookups,
                    college_id=college_id,
                    campus_id=campus_id,
                    row_number=offset,
                    classroom_column="Practical Classroom Name",
                    issues=issues,
                    suggestions=suggestions,
                    context=context,
                    overrides=overrides,
                )
            )
        if mscris_times or not _is_null(values["MSCRIS Class Name"]):
            if not mscris_times:
                mscris_times = [(rules.MSCRIS_WEEKDAY, dt.time(9, 0), dt.time(14, 0))]
            sessions.extend(
                _build_sessions(
                    profile=profile,
                    times=mscris_times,
                    classrooms=mscris_rooms,
                    trainers=mscris_trainers,
                    stream="MSCRIS",
                    lookups=lookups,
                    college_id=college_id,
                    campus_id=campus_id,
                    row_number=offset,
                    classroom_column="MSCRIS Class Name",
                    issues=issues,
                    suggestions=suggestions,
                    context=context,
                    overrides=overrides,
                )
            )

        has_practical = any(item.stream == "PRACTICAL" for item in sessions)
        if mode == "F2FV" and (has_practical or profile.has_practical and practical_times):
            issues.append(Discrepancy(KIND_F2FV_PRACTICAL, "refuse", offset, "Mode of Delivery", mode, "A unit with practical cannot be fully virtual."))
        expected = rules.mode_matrix(has_practical, mode) if mode else None
        if mode and expected is None and not (mode == "F2FV" and has_practical):
            pass
        if mode and expected and _has_classroom_values(profile, values):
            theory_physical = sum(1 for item in sessions if item.stream == "THEORY" and item.delivery_mode == "PHYSICAL")
            theory_virtual = sum(1 for item in sessions if item.stream == "THEORY" and item.delivery_mode == "VIRTUAL")
            practical_physical = sum(1 for item in sessions if item.stream == "PRACTICAL" and item.delivery_mode == "PHYSICAL")
            if (
                theory_physical != expected["theory_physical"]
                or theory_virtual != expected["theory_virtual"]
                or practical_physical != expected["practical_physical"]
            ):
                issues.append(
                    Discrepancy(
                        KIND_MODE_CONTRADICTION,
                        "refuse",
                        offset,
                        "Mode of Delivery",
                        mode,
                        "Mode of Delivery disagrees with the classroom columns. Correct the row before applying.",
                        edit_fields=_mode_classroom_edit_fields(profile, values),
                    )
                )
        teaching_days = rules.teaching_day_count([(item.stream, item.weekday) for item in sessions])
        if teaching_days and teaching_days != rules.TEACHING_DAYS_PER_WEEK:
            issues.append(
                Discrepancy(
                    KIND_TEACHING_DAYS,
                    "warn",
                    offset,
                    "Theory Class Days and Times",
                    str(teaching_days),
                    "A unit is scheduled on other than two days a week.",
                )
            )

        refused_row = any(item.severity == "refuse" and item.row_number == offset for item in issues)
        if not start or not end or not duration or not uoc_type or not mode:
            refused_row = True
        delivery = PlannedDelivery(
            source_row=offset,
            training_package=package,
            college_id=college_id,
            campus_id=campus_id,
            qualification_id=qual.id if qual else None,
            qualification_code=values["Qualification Id"].upper(),
            college_value=values["College"],
            campus_value=values["Campus Location"],
            duration_weeks=duration or 0,
            group_code="NA" if not profile.has_group else (values["Group"] or "NA"),
            unit_id=unit.id if unit else None,
            unit_code=values["Units of Competency ID"].upper(),
            uoc_type=uoc_type or "THEORY_ONLY",
            mode_of_delivery=mode or "F2FP",
            start_date=start or dt.date.min,
            end_date=end or dt.date.min,
            classroom_size=classroom_size,
            remarks=None if _is_null(values["Remarks"]) else values["Remarks"],
            sessions=sessions,
            intake_labels=[],
            intake_match_status="NOT_FOUND",
            raw_values=values,
            refused=refused_row,
            needs_correction=any(item.kind == KIND_MODE_CONTRADICTION and item.row_number == offset for item in issues),
        )
        if not refused_row:
            # Python treats None == None as true, so keying on the raw
            # identifiers collapsed two rows with two *different* unresolved
            # values into one delivery. PostgreSQL treats NULLs as distinct, so
            # the in-memory and database behaviour disagreed. Fall back to the
            # normalised text whenever the identifier is absent.
            key = (
                package,
                college_id if college_id is not None else f"TEXT:{normalise_suggestion_value(values['College'])}",
                campus_id if campus_id is not None else f"TEXT:{normalise_suggestion_value(values['Campus Location'])}",
                delivery.qualification_id
                if delivery.qualification_id is not None
                else f"TEXT:{normalise_suggestion_value(values['Qualification Id'])}",
                delivery.duration_weeks,
                delivery.unit_id
                if delivery.unit_id is not None
                else f"TEXT:{normalise_suggestion_value(values['Units of Competency ID'])}",
                delivery.start_date,
                delivery.end_date,
            )
            if key in keys:
                issues.append(Discrepancy(KIND_KEY_CONFLICT, "refuse", offset, None, values["Units of Competency ID"], "The business key repeats with conflicting values."))
                delivery.refused = True
                keys[key].refused = True
            else:
                keys[key] = delivery
            _match_intakes(session, delivery)
            if delivery.intake_match_status == "NOT_FOUND":
                issues.append(Discrepancy(KIND_NO_INTAKE, "warn", offset, "Units of Competency ID", delivery.unit_code, "No rolling-timetable intake matches this delivery."))
        planned.append(delivery)

    skip_rows: set[int] = set()
    for item in issues:
        if not overrides.is_excepted(item) or item.kind == KIND_UNRESOLVED:
            continue
        item.severity = "warn"
        if item.kind == KIND_MISSING_HEADER:
            item.message = f"Column '{item.value}' ignored as an exception."
        elif item.kind in ROW_SKIP_KINDS and item.row_number:
            skip_rows.add(item.row_number)
            item.message = f"{item.message} This row will be skipped."
        elif item.kind == KIND_NAME_MISMATCH:
            item.message = f"{item.message} Accepted as an exception."
    for delivery in planned:
        if delivery.source_row in skip_rows:
            delivery.refused = True

    review = _review(
        package, file_name, len(rows), planned, issues, suggestions, raise_suggestions, existing_deliveries
    )
    return review, planned, suggestions


def _review(
    package: str,
    file_name: str,
    rows_read: int,
    planned: list[PlannedDelivery],
    issues: list[Discrepancy],
    suggestions: dict,
    raise_suggestions: bool = True,
    existing_deliveries: int = 0,
) -> ImportReview:
    refused = any(item.severity == "refuse" for item in issues)
    writable = [item for item in planned if not item.refused]
    return ImportReview(
        status="refused" if refused else "accepted",
        training_package=package,
        file_name=file_name,
        rows_read=rows_read,
        deliveries_that_would_be_written=len(writable),
        sessions_that_would_be_written=sum(len(item.sessions) for item in writable),
        qualifications=sorted({item.qualification_code for item in writable}),
        units=sorted({item.unit_code for item in writable}),
        intakes_matched=sum(1 for item in writable if item.intake_match_status == "MATCHED"),
        intakes_not_matched=sum(1 for item in writable if item.intake_match_status == "NOT_FOUND"),
        # Only raised entries; an accepted exception is recorded but is not a
        # suggestion awaiting a decision.
        suggestions_that_would_be_raised=sum(
            1 for item in suggestions.values() if item.get("kind", "RAISE") == "RAISE"
        ),
        discrepancies=issues,
        refused=refused,
        can_apply=not refused,
        raise_suggestions=raise_suggestions,
        existing_deliveries=existing_deliveries,
    )


def review_to_dict(review: ImportReview) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    discrepancies = []
    for item in review.discrepancies:
        edit_fields = list(item.edit_fields)
        if not edit_fields and item.row_number and item.row_number >= 2 and item.column:
            edit_fields = [{"column": item.column, "value": item.value or ""}]
        edit_fields = [
            {"column": str(field.get("column") or item.column or ""), "value": str(field.get("value") or "")}
            for field in edit_fields
        ]
        payload = {
            "kind": item.kind,
            "severity": item.severity,
            "row_number": item.row_number,
            "column": item.column,
            "value": item.value,
            "message": item.message,
            "issue_id": issue_id(item),
            "edit_fields": edit_fields,
            "can_edit": bool(edit_fields),
            "can_raise_suggestion": item.kind == KIND_UNRESOLVED,
            "can_except": item.kind in {KIND_UNRESOLVED, KIND_NAME_MISMATCH, *ROW_SKIP_KINDS}
            or (item.kind == KIND_MISSING_HEADER and bool(item.column)),
        }
        discrepancies.append(payload)
        grouped[item.kind].append(payload)
    return {
        "status": review.status,
        "training_package": review.training_package,
        "file_name": review.file_name,
        "rows_read": review.rows_read,
        "deliveries_that_would_be_written": review.deliveries_that_would_be_written,
        "sessions_that_would_be_written": review.sessions_that_would_be_written,
        "qualifications": review.qualifications,
        "units": review.units,
        "intakes_matched": review.intakes_matched,
        "intakes_not_matched": review.intakes_not_matched,
        "suggestions_that_would_be_raised": review.suggestions_that_would_be_raised,
        "discrepancies": discrepancies,
        "discrepancies_by_kind": dict(grouped),
        "refused": review.refused,
        "can_apply": review.can_apply,
        "raise_suggestions": review.raise_suggestions,
        "existing_deliveries": review.existing_deliveries,
    }


def _upsert_exceptions(session: Session, suggestions: dict, user: User) -> tuple[int, list[str]]:
    """Write the accepted exceptions collected during validation (section 2.9).

    Written here, at apply time, in the same transaction as the rows that depend
    on them — a review that is abandoned leaves nothing behind. A value already
    approved or rejected is not silently reopened; it returns a warning instead.
    """
    from app.services.reference_suggestions import record_reference_exception

    recorded = 0
    warnings: list[str] = []
    for item in suggestions.values():
        if item.get("kind") != "EXCEPT":
            continue
        row, warning = record_reference_exception(
            session,
            entity_type=item["entity_type"],
            raw_value=item["raw_value"],
            context=item["context"],
            source="ALLOCATION_IMPORT",
            user_id=user.id,
            occurrences=item["occurrence_count"],
        )
        if warning:
            warnings.append(warning)
            continue
        if row is not None:
            recorded += 1
            record_activity(
                session,
                user=user,
                action="UPDATE",
                page_or_function="Reference data - suggestion queue",
                detail=(
                    f"Accepted {item['entity_type']} '{item['raw_value']}' as an exception "
                    f"on {item['occurrence_count']} record(s)."
                ),
                record_reference=str(row.id),
                result="COMPLETED",
            )
    return recorded, warnings


def _upsert_suggestions(session: Session, suggestions: dict, now: dt.datetime) -> int:
    handled = 0
    for item in suggestions.values():
        if item.get("kind", "RAISE") != "RAISE":
            continue  # exceptions take their own path (2.9)
        handled += 1
        existing = session.execute(
            select(ReferenceSuggestion).where(
                ReferenceSuggestion.entity_type == item["entity_type"],
                ReferenceSuggestion.normalised_value == item["normalised_value"],
                ReferenceSuggestion.context_key == item["context_key"],
            )
        ).scalar_one_or_none()
        if existing:
            existing.occurrence_count += item["occurrence_count"]
            existing.last_seen_at = now
            if existing.status != "PENDING":
                was_rejected = existing.status == "REJECTED"
                existing.status = "PENDING"
                existing.resolved_at = None
                existing.resolved_by_user_id = None
                existing.resolved_entity_id = None
                existing.accepted_by_user_id = None
                existing.accepted_at = None
                if was_rejected:
                    # A mistaken rejection is recoverable: the rows quarantined
                    # by it come back with the entry (2.5.4).
                    from app.services.reference_suggestion_service import clear_quarantine_for

                    clear_quarantine_for(session, existing)
        else:
            session.add(
                ReferenceSuggestion(
                    entity_type=item["entity_type"],
                    raw_value=item["raw_value"],
                    normalised_value=item["normalised_value"],
                    context=item["context"],
                    context_key=item["context_key"],
                    source="ALLOCATION_IMPORT",
                    occurrence_count=item["occurrence_count"],
                    first_seen_at=now,
                    last_seen_at=now,
                    status="PENDING",
                )
            )
    session.flush()
    # The number of values now sitting in the queue — new rows plus the ones an
    # existing entry absorbed. Entries collected as exceptions are not counted:
    # they are recorded by `_upsert_exceptions`, and counting them here reported
    # suggestions the queue never held.
    return handled


def apply_rows(
    session: Session,
    *,
    training_package: str,
    file_name: str,
    file_size_bytes: int | None,
    payload: bytes,
    apply_mode: str,
    user: User,
    raise_suggestions: bool = True,
    overrides: ImportOverrides | None = None,
) -> dict:
    review, planned, suggestions = validate_bytes(
        session,
        training_package=training_package,
        file_name=file_name,
        payload=payload,
        raise_suggestions=raise_suggestions,
        overrides=overrides,
    )
    if review.refused:
        raise AllocationImportError("The file was refused. Nothing was written.")
    package = review.training_package
    writable = [item for item in planned if not item.refused]
    now = dt.datetime.now(dt.timezone.utc)
    removed = 0
    if apply_mode == "REPLACE":
        removed = session.execute(
            select(func.count()).select_from(AllocationDelivery).where(AllocationDelivery.training_package == package)
        ).scalar_one()
        session.execute(delete(AllocationDelivery).where(AllocationDelivery.training_package == package))
        session.flush()
        for item in writable:
            _insert_delivery(session, item)
    else:
        for item in writable:
            existing = session.execute(
                select(AllocationDelivery).where(
                    AllocationDelivery.training_package == package,
                    AllocationDelivery.college_id == item.college_id,
                    AllocationDelivery.campus_id == item.campus_id,
                    AllocationDelivery.qualification_id == item.qualification_id,
                    AllocationDelivery.duration_weeks == item.duration_weeks,
                    AllocationDelivery.unit_id == item.unit_id,
                    AllocationDelivery.start_date == item.start_date,
                    AllocationDelivery.end_date == item.end_date,
                )
            ).scalar_one_or_none()
            if existing:
                existing.group_code = item.group_code
                existing.uoc_type = item.uoc_type
                existing.mode_of_delivery = item.mode_of_delivery
                existing.classroom_size = item.classroom_size
                existing.remarks = item.remarks
                existing.intake_match_status = item.intake_match_status
                # Re-importing after a value is approved must clear the stale
                # text, so the row stops looking unresolved (2.3.3).
                existing.college_text = None if item.college_id else (item.college_value or None)
                existing.campus_text = None if item.campus_id else (item.campus_value or None)
                existing.qualification_text = (
                    None if item.qualification_id else (item.qualification_code or None)
                )
                existing.unit_text = None if item.unit_id else (item.unit_code or None)
                session.execute(
                    delete(AllocationSession).where(
                        AllocationSession.delivery_id == existing.id,
                        AllocationSession.training_package == package,
                    )
                )
                session.execute(
                    delete(AllocationDeliveryIntake).where(
                        AllocationDeliveryIntake.delivery_id == existing.id,
                        AllocationDeliveryIntake.training_package == package,
                    )
                )
                session.flush()
                _insert_children(session, existing, item)
            else:
                _insert_delivery(session, item)
    session.flush()
    suggestion_count = _upsert_suggestions(session, suggestions, now)
    exception_count, exception_warnings = _upsert_exceptions(session, suggestions, user)
    batch = AllocationImportBatch(
        training_package=package,
        file_name=file_name,
        file_size_bytes=file_size_bytes,
        uploaded_by_user_id=user.id,
        uploaded_at=now,
        apply_mode=apply_mode,
        rows_read=review.rows_read,
        deliveries_written=len(writable),
        sessions_written=sum(len(item.sessions) for item in writable),
        deliveries_removed=removed if apply_mode == "REPLACE" else 0,
        suggestions_raised=suggestion_count,
        raise_suggestions=raise_suggestions,
        status="COMPLETED",
        completed_at=now,
    )
    session.add(batch)
    session.flush()
    if writable:
        session.execute(
            insert(AllocationSourceRow),
            [
                {
                    "batch_id": batch.id,
                    "training_package": item.training_package,
                    "source_row_number": item.source_row,
                    "raw_values": item.raw_values,
                    "delivery_id": None,
                }
                for item in planned
            ],
        )
    record_activity(
        session,
        user=user,
        action="IMPORT",
        page_or_function="Page 1 - Timetable View and Management",
        detail=(
            f"Imported {file_name} under {package} ({apply_mode}): read {review.rows_read}, "
            f"wrote {len(writable)} deliveries and {sum(len(item.sessions) for item in writable)} sessions."
        ),
        record_reference=f"{package}:{file_name}:{len(writable)}",
        result="COMPLETED",
    )
    return {
        "rows_read": review.rows_read,
        "deliveries_written": len(writable),
        "sessions_written": sum(len(item.sessions) for item in writable),
        "deliveries_removed": batch.deliveries_removed,
        "suggestions_raised": suggestion_count,
        "exceptions_recorded": exception_count,
        # A value already approved or rejected is not reopened as an exception;
        # the import says so rather than failing quietly (2.9.2).
        "warnings": exception_warnings,
        "apply_mode": apply_mode,
    }


def _insert_delivery(session: Session, item: PlannedDelivery) -> AllocationDelivery:
    delivery = AllocationDelivery(
        training_package=item.training_package,
        college_id=item.college_id,
        campus_id=item.campus_id,
        qualification_id=item.qualification_id,
        duration_weeks=item.duration_weeks,
        group_code=item.group_code,
        unit_id=item.unit_id,
        uoc_type=item.uoc_type,
        mode_of_delivery=item.mode_of_delivery,
        start_date=item.start_date,
        end_date=item.end_date,
        classroom_size=item.classroom_size,
        remarks=item.remarks,
        intake_match_status=item.intake_match_status,
        # Written only when the identifier is absent, so an id and text are
        # never both present and the row's state stays unambiguous (2.3.2).
        college_text=None if item.college_id else (item.college_value or None),
        campus_text=None if item.campus_id else (item.campus_value or None),
        qualification_text=None if item.qualification_id else (item.qualification_code or None),
        unit_text=None if item.unit_id else (item.unit_code or None),
    )
    session.add(delivery)
    session.flush()
    _insert_children(session, delivery, item)
    return delivery


def _insert_children(session: Session, delivery: AllocationDelivery, item: PlannedDelivery) -> None:
    if item.sessions:
        session.execute(
            insert(AllocationSession),
            [
                {
                    "training_package": item.training_package,
                    "delivery_id": delivery.id,
                    "stream": row.stream,
                    "weekday": row.weekday,
                    "start_time": row.start_time,
                    "end_time": row.end_time,
                    "delivery_mode": row.delivery_mode,
                    "facility_id": row.facility_id,
                    "virtual_kind": row.virtual_kind,
                    "classroom_text": row.classroom_text,
                    "trainer_id": row.trainer_id,
                    "trainer_text": row.trainer_text,
                }
                for row in item.sessions
            ],
        )
    if item.intake_labels:
        session.execute(
            insert(AllocationDeliveryIntake),
            [
                {
                    "delivery_id": delivery.id,
                    "training_package": item.training_package,
                    "intake_label": label,
                    "group_code": group,
                }
                for label, group in item.intake_labels
            ],
        )
