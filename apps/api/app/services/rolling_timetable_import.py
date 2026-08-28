"""Parse, validate, review and apply a flat rolling-timetable file.

The website upload and the command-line script both call this module. They must
accept and reject the same bytes.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from app.db.enums import TRAINING_PACKAGE_VALUES
from app.models.qualification import Unit
from app.models.timetable import RollingTimetableWeek
from app.models.user import User
from app.services.activity import record_activity

TYPE_UNIT = "UNIT"
TYPE_BREAK = "BREAK"
TYPE_ASSESSMENT = "ASSESSMENT_WEEK"
SCHEDULE_TYPES = {TYPE_UNIT, TYPE_BREAK, TYPE_ASSESSMENT}

INTAKE_LABEL_RE = re.compile(
    r"^(?P<code>.+)_(?P<duration>\d+)_(?P<date>.+)_(?P<group>.+)_Intake$"
)
INTAKE_DATE_FORMAT = "%d %b %Y"

FLAT_COLUMNS: tuple[str, ...] = (
    "qualification_code",
    "duration_weeks",
    "intake_label",
    "intake_group",
    "intake_start_date",
    "week_no",
    "week_start_date",
    "week_end_date",
    "schedule_type",
    "schedule_value",
    "unit_code",
    "unit_count",
    "unit_delivery_span_weeks",
)

KIND_MISSING_HEADER = "missing_or_unknown_header"
KIND_BAD_DATE = "unreadable_date"
KIND_WEEK_CALENDAR = "week_not_monday_to_sunday"
KIND_NOT_INTEGER = "not_a_whole_number"
KIND_BAD_SCHEDULE_TYPE = "invalid_schedule_type"
KIND_UNIT_FIELDS = "unit_fields_mismatch"
KIND_KEY_CONFLICT = "business_key_conflict"
KIND_BAD_INTAKE_LABEL = "invalid_intake_label"
KIND_INTAKE_ROW_MISMATCH = "intake_label_disagrees_with_row"
KIND_WEEK_GAP = "week_number_gap"
KIND_DERIVED_DATE = "derived_date_disagrees"
KIND_EMPTY_FOR_PACKAGE = "empty_or_no_rows_for_package"
KIND_PACKAGE_MISMATCH = "qualification_not_in_selected_package"
KIND_UNKNOWN_UNIT = "unit_code_not_in_register"
KIND_DURATION_ALREADY_STORED = "qualification_stored_under_other_duration"
KIND_INTAKE_WITHOUT_UNIT = "intake_has_no_unit"
KIND_DURATION_SPAN = "duration_disagrees_with_delivery_span"

REFUSE_KINDS = {
    KIND_MISSING_HEADER,
    KIND_BAD_DATE,
    KIND_WEEK_CALENDAR,
    KIND_NOT_INTEGER,
    KIND_BAD_SCHEDULE_TYPE,
    KIND_UNIT_FIELDS,
    KIND_KEY_CONFLICT,
    KIND_BAD_INTAKE_LABEL,
    KIND_INTAKE_ROW_MISMATCH,
    KIND_WEEK_GAP,
    KIND_DERIVED_DATE,
    KIND_EMPTY_FOR_PACKAGE,
}

# Visualizer query cost: one SELECT. Proven in tests/test_rolling_timetable_import.py.
VISUALIZER_QUERY_COUNT = 1


@dataclass
class Discrepancy:
    kind: str
    severity: str
    row_number: int | None
    column: str | None
    value: str | None
    message: str


@dataclass
class ParsedRow:
    source_row: int
    qualification_code: str
    duration_weeks: int
    intake_label: str
    intake_group: str
    intake_start_date: dt.date
    week_no: int
    week_start_date: dt.date
    week_end_date: dt.date
    schedule_type: str
    schedule_value: str
    unit_code: str | None
    unit_count: int
    unit_delivery_span_weeks: int | None
    unit_slot: int = 1

    def business_key(self) -> tuple:
        return (
            self.qualification_code,
            self.duration_weeks,
            self.intake_label,
            self.week_no,
            self.unit_slot,
        )

    def as_mapping(self, training_package: str) -> dict:
        return {
            "training_package": training_package,
            "qualification_code": self.qualification_code,
            "duration_weeks": self.duration_weeks,
            "intake_label": self.intake_label,
            "intake_group": self.intake_group,
            "intake_start_date": self.intake_start_date,
            "week_no": self.week_no,
            "week_start_date": self.week_start_date,
            "week_end_date": self.week_end_date,
            "schedule_type": self.schedule_type,
            "schedule_value": self.schedule_value,
            "unit_code": self.unit_code,
            "unit_count": self.unit_count,
            "unit_delivery_span_weeks": self.unit_delivery_span_weeks,
            "unit_slot": self.unit_slot,
        }


@dataclass
class QualificationSummary:
    qualification_code: str
    duration_weeks: int
    training_package: str
    row_count: int
    intake_count: int


@dataclass
class ImportReview:
    status: str
    training_package: str
    file_name: str
    rows_read: int
    rows_that_would_be_written: int
    qualifications: list[QualificationSummary]
    matching_qualifications: list[QualificationSummary]
    non_matching_qualifications: list[QualificationSummary]
    counts: dict[str, int]
    discrepancies: list[Discrepancy]
    existing_qualifications_replaced: list[str]
    refused: bool
    can_proceed_with_package: bool

    def grouped_discrepancies(self) -> dict[str, list[Discrepancy]]:
        grouped: dict[str, list[Discrepancy]] = defaultdict(list)
        for item in self.discrepancies:
            grouped[item.kind].append(item)
        return dict(grouped)


@dataclass
class ImportApplyResult:
    rows_written: int
    qualifications_replaced: list[str]
    qualifications_skipped: list[str]
    rows_read: int


class RollingImportError(ValueError):
    """A structural fault that refuses the file before a review can be useful."""


def _clean(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dt.datetime):
        return value.date().isoformat()
    if isinstance(value, dt.date):
        return value.isoformat()
    text = str(value).strip()
    if text.endswith(".0") and text.replace(".", "", 1).isdigit() is False:
        pass
    return text


def _normalise_header(value: object) -> str:
    return _clean(value).lower().replace(" ", "_")


def _parse_int(raw: str, *, column: str, row_number: int, issues: list[Discrepancy]) -> int | None:
    if raw == "":
        issues.append(
            Discrepancy(KIND_NOT_INTEGER, "refuse", row_number, column, raw, f"{column} is empty.")
        )
        return None
    try:
        if isinstance(raw, bool):  # pragma: no cover
            raise ValueError
        number = int(str(raw).strip())
    except (TypeError, ValueError):
        issues.append(
            Discrepancy(KIND_NOT_INTEGER, "refuse", row_number, column, raw, f"{column} is not a whole number.")
        )
        return None
    return number


def _parse_optional_int(raw: str, *, column: str, row_number: int, issues: list[Discrepancy]) -> int | None:
    if raw == "":
        return None
    return _parse_int(raw, column=column, row_number=row_number, issues=issues)


def _parse_date(raw: object, *, column: str, row_number: int, issues: list[Discrepancy]) -> dt.date | None:
    if isinstance(raw, dt.datetime):
        return raw.date()
    if isinstance(raw, dt.date):
        return raw
    text = _clean(raw)
    if not text:
        issues.append(Discrepancy(KIND_BAD_DATE, "refuse", row_number, column, text, f"{column} is empty."))
        return None
    if re.search(r"\d+/\d+/\d+", text):
        issues.append(
            Discrepancy(KIND_BAD_DATE, "refuse", row_number, column, text, f"{column} is ambiguous. Use ISO dates.")
        )
        return None
    try:
        return dt.date.fromisoformat(text[:10])
    except ValueError:
        pass
    try:
        return dt.datetime.strptime(text, INTAKE_DATE_FORMAT).date()
    except ValueError:
        issues.append(
            Discrepancy(KIND_BAD_DATE, "refuse", row_number, column, text, f"{column} cannot be read as a date.")
        )
        return None


def parse_intake_label(label: str) -> tuple[str, int, dt.date, str] | None:
    match = INTAKE_LABEL_RE.match(label.strip())
    if not match:
        return None
    try:
        start = dt.datetime.strptime(match.group("date"), INTAKE_DATE_FORMAT).date()
    except ValueError:
        return None
    return match.group("code").upper(), int(match.group("duration")), start, match.group("group")


def package_of(qualification_code: str) -> str:
    return qualification_code[:3].upper()


def _read_tabular(file_name: str, payload: bytes) -> tuple[list[str], list[list[object]]]:
    lower = file_name.lower()
    if lower.endswith(".csv"):
        text = payload.decode("utf-8-sig")
        reader = csv.reader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            return [], []
        return [_clean(cell) for cell in rows[0]], rows[1:]
    if lower.endswith(".xlsx"):
        import openpyxl

        workbook = openpyxl.load_workbook(io.BytesIO(payload), data_only=True, read_only=True)
        try:
            sheet = workbook.worksheets[0]
            values = list(sheet.iter_rows(values_only=True))
        finally:
            workbook.close()
        if not values:
            return [], []
        return [_clean(cell) for cell in values[0]], [list(row) for row in values[1:]]
    raise RollingImportError("The file must be a CSV or XLSX workbook.")


def _map_headers(headers: list[str], issues: list[Discrepancy]) -> dict[str, int] | None:
    index_by_name: dict[str, int] = {}
    unknown: list[str] = []
    for index, header in enumerate(headers):
        name = _normalise_header(header)
        if not name:
            continue
        if name not in FLAT_COLUMNS:
            unknown.append(header)
            continue
        if name not in index_by_name:
            index_by_name[name] = index
    missing = [name for name in FLAT_COLUMNS if name not in index_by_name]
    if missing or unknown:
        issues.append(
            Discrepancy(
                KIND_MISSING_HEADER,
                "refuse",
                1,
                None,
                ", ".join(unknown + missing),
                (
                    ("Unrecognised header(s): " + ", ".join(unknown) + ". " if unknown else "")
                    + ("Missing column(s): " + ", ".join(missing) + "." if missing else "")
                ).strip(),
            )
        )
        return None
    return index_by_name


def _cell(row: list[object], columns: dict[str, int], name: str) -> object:
    index = columns[name]
    return row[index] if index < len(row) else ""


def _parse_body(
    body: list[list[object]], columns: dict[str, int], issues: list[Discrepancy]
) -> list[ParsedRow]:
    parsed: list[ParsedRow] = []
    for offset, raw in enumerate(body, start=2):
        if all(_clean(cell) == "" for cell in raw):
            continue
        qualification = _clean(_cell(raw, columns, "qualification_code")).upper()
        intake_label = _clean(_cell(raw, columns, "intake_label"))
        intake_group_cell = _clean(_cell(raw, columns, "intake_group"))
        schedule_type = _clean(_cell(raw, columns, "schedule_type")).upper().replace(" ", "_")
        if schedule_type == "ASSESSMENTWEEK":
            schedule_type = TYPE_ASSESSMENT
        schedule_value = _clean(_cell(raw, columns, "schedule_value"))
        unit_raw = _clean(_cell(raw, columns, "unit_code"))

        duration = _parse_int(
            _clean(_cell(raw, columns, "duration_weeks")),
            column="duration_weeks",
            row_number=offset,
            issues=issues,
        )
        week_no = _parse_int(
            _clean(_cell(raw, columns, "week_no")), column="week_no", row_number=offset, issues=issues
        )
        unit_count = _parse_int(
            _clean(_cell(raw, columns, "unit_count")) or "0",
            column="unit_count",
            row_number=offset,
            issues=issues,
        )
        span = _parse_optional_int(
            _clean(_cell(raw, columns, "unit_delivery_span_weeks")),
            column="unit_delivery_span_weeks",
            row_number=offset,
            issues=issues,
        )
        intake_start = _parse_date(
            _cell(raw, columns, "intake_start_date"), column="intake_start_date", row_number=offset, issues=issues
        )
        week_start = _parse_date(
            _cell(raw, columns, "week_start_date"), column="week_start_date", row_number=offset, issues=issues
        )
        week_end = _parse_date(
            _cell(raw, columns, "week_end_date"), column="week_end_date", row_number=offset, issues=issues
        )

        if schedule_type not in SCHEDULE_TYPES:
            issues.append(
                Discrepancy(
                    KIND_BAD_SCHEDULE_TYPE,
                    "refuse",
                    offset,
                    "schedule_type",
                    schedule_type,
                    "schedule_type must be UNIT, BREAK or ASSESSMENT_WEEK.",
                )
            )

        if week_start is not None and week_start.weekday() != 0:
            issues.append(
                Discrepancy(
                    KIND_WEEK_CALENDAR,
                    "refuse",
                    offset,
                    "week_start_date",
                    week_start.isoformat(),
                    "week_start_date must be a Monday.",
                )
            )
        if week_start is not None and week_end is not None and week_end != week_start + dt.timedelta(days=6):
            issues.append(
                Discrepancy(
                    KIND_WEEK_CALENDAR,
                    "refuse",
                    offset,
                    "week_end_date",
                    week_end.isoformat(),
                    "week_end_date must be exactly six days after week_start_date.",
                )
            )

        unit_code = unit_raw or None
        if schedule_type == TYPE_UNIT:
            if not unit_code:
                issues.append(
                    Discrepancy(
                        KIND_UNIT_FIELDS,
                        "refuse",
                        offset,
                        "unit_code",
                        unit_raw,
                        "UNIT rows must carry a unit_code.",
                    )
                )
            if unit_count is not None and unit_count < 1:
                issues.append(
                    Discrepancy(
                        KIND_UNIT_FIELDS,
                        "refuse",
                        offset,
                        "unit_count",
                        str(unit_count),
                        "UNIT rows must have unit_count of at least 1.",
                    )
                )
        elif schedule_type in {TYPE_BREAK, TYPE_ASSESSMENT}:
            if unit_code:
                issues.append(
                    Discrepancy(
                        KIND_UNIT_FIELDS,
                        "refuse",
                        offset,
                        "unit_code",
                        unit_code,
                        "Break and Assessment Week rows must not carry a unit_code.",
                    )
                )
                unit_code = None
            unit_count = 0
            span = None

        parsed_label = parse_intake_label(intake_label)
        if parsed_label is None:
            issues.append(
                Discrepancy(
                    KIND_BAD_INTAKE_LABEL,
                    "refuse",
                    offset,
                    "intake_label",
                    intake_label,
                    "intake_label must match Qualification_Duration_Date_Group_Intake.",
                )
            )
        else:
            label_code, label_duration, label_start, label_group = parsed_label
            if qualification and label_code != qualification:
                issues.append(
                    Discrepancy(
                        KIND_INTAKE_ROW_MISMATCH,
                        "refuse",
                        offset,
                        "intake_label",
                        intake_label,
                        "intake_label qualification does not match qualification_code.",
                    )
                )
            if duration is not None and label_duration != duration:
                issues.append(
                    Discrepancy(
                        KIND_INTAKE_ROW_MISMATCH,
                        "refuse",
                        offset,
                        "intake_label",
                        intake_label,
                        "intake_label duration does not match duration_weeks.",
                    )
                )
            if not intake_group_cell:
                intake_group_cell = label_group
            if intake_start is None:
                intake_start = label_start

        if None in (duration, week_no, unit_count, intake_start, week_start, week_end) or not qualification:
            continue
        if schedule_type not in SCHEDULE_TYPES:
            continue
        if schedule_type == TYPE_UNIT and not unit_code:
            continue

        parsed.append(
            ParsedRow(
                source_row=offset,
                qualification_code=qualification,
                duration_weeks=duration,
                intake_label=intake_label,
                intake_group=intake_group_cell,
                intake_start_date=intake_start,
                week_no=week_no,
                week_start_date=week_start,
                week_end_date=week_end,
                schedule_type=schedule_type,
                schedule_value=schedule_value,
                unit_code=unit_code,
                unit_count=unit_count,
                unit_delivery_span_weeks=span,
            )
        )
    return parsed


def _assign_slots_and_dedupe(rows: list[ParsedRow], issues: list[Discrepancy]) -> list[ParsedRow]:
    grouped: dict[tuple[str, int, str, int], list[ParsedRow]] = defaultdict(list)
    for row in rows:
        grouped[(row.qualification_code, row.duration_weeks, row.intake_label, row.week_no)].append(row)

    kept: list[ParsedRow] = []
    for group in grouped.values():
        group.sort(key=lambda item: (item.unit_code or "", item.source_row))
        unique: list[ParsedRow] = []
        for row in group:
            match = next(
                (
                    existing
                    for existing in unique
                    if existing.schedule_type == row.schedule_type
                    and existing.schedule_value == row.schedule_value
                    and existing.unit_code == row.unit_code
                ),
                None,
            )
            if match is not None:
                continue
            clash = next(
                (
                    existing
                    for existing in unique
                    if existing.unit_code == row.unit_code and existing.schedule_value != row.schedule_value
                ),
                None,
            )
            if clash is not None:
                issues.append(
                    Discrepancy(
                        KIND_KEY_CONFLICT,
                        "refuse",
                        row.source_row,
                        None,
                        row.schedule_value,
                        "The same intake and week repeats with conflicting values.",
                    )
                )
                continue
            unique.append(row)
        for slot, row in enumerate(unique, start=1):
            row.unit_slot = slot
            kept.append(row)
    return kept


def _stamp_delivery_spans(rows: list[ParsedRow]) -> None:
    by_intake: dict[tuple[str, int, str], list[ParsedRow]] = defaultdict(list)
    for row in rows:
        by_intake[(row.qualification_code, row.duration_weeks, row.intake_label)].append(row)

    for group in by_intake.values():
        group.sort(key=lambda row: (row.week_no, row.unit_slot))
        pending_value: str | None = None
        pending_rows: list[ParsedRow] = []
        pending_start: dt.date | None = None
        pending_end: dt.date | None = None

        def close() -> None:
            nonlocal pending_value, pending_rows, pending_start, pending_end
            if pending_value is None or pending_start is None or pending_end is None:
                pending_value = None
                pending_rows = []
                return
            span = ((pending_end - pending_start).days + 1) // 7
            for item in pending_rows:
                if item.unit_delivery_span_weeks is None:
                    item.unit_delivery_span_weeks = span
            pending_value = None
            pending_rows = []
            pending_start = None
            pending_end = None

        for row in group:
            if row.schedule_type == TYPE_UNIT:
                if pending_value is None:
                    pending_value = row.schedule_value
                    pending_rows = [row]
                    pending_start = row.week_start_date
                    pending_end = row.week_end_date
                elif row.schedule_value == pending_value:
                    pending_rows.append(row)
                    pending_end = row.week_end_date
                else:
                    close()
                    pending_value = row.schedule_value
                    pending_rows = [row]
                    pending_start = row.week_start_date
                    pending_end = row.week_end_date
            elif pending_value is not None:
                pending_end = row.week_end_date
        close()


def _assert_week_calendar(rows: list[ParsedRow], issues: list[Discrepancy]) -> None:
    by_loop: dict[tuple[str, int], list[ParsedRow]] = defaultdict(list)
    for row in rows:
        by_loop[(row.qualification_code, row.duration_weeks)].append(row)

    for (code, duration), group in by_loop.items():
        by_week: dict[int, dt.date] = {}
        for row in group:
            existing = by_week.get(row.week_no)
            if existing is None:
                by_week[row.week_no] = row.week_start_date
            elif existing != row.week_start_date:
                issues.append(
                    Discrepancy(
                        KIND_WEEK_GAP,
                        "refuse",
                        row.source_row,
                        "week_start_date",
                        row.week_start_date.isoformat(),
                        f"{code} week {row.week_no} has more than one start date.",
                    )
                )
        if not by_week:
            continue
        lowest = min(by_week)
        highest = max(by_week)
        origin = by_week[lowest]
        if set(by_week) != set(range(lowest, highest + 1)):
            missing = [week for week in range(lowest, highest + 1) if week not in by_week]
            # Gaps are allowed when every intake is idle that week, so long as
            # stored dates still sit on the derived Monday grid.
            _ = missing
        for week_no, start in by_week.items():
            derived = origin + dt.timedelta(days=7 * (week_no - lowest))
            if derived != start:
                issues.append(
                    Discrepancy(
                        KIND_DERIVED_DATE,
                        "refuse",
                        None,
                        "week_start_date",
                        start.isoformat(),
                        f"{code} week {week_no} starts on {start.isoformat()}, "
                        f"but the derived calendar says {derived.isoformat()}.",
                    )
                )


def _summaries(rows: Iterable[ParsedRow]) -> list[QualificationSummary]:
    grouped: dict[tuple[str, int], list[ParsedRow]] = defaultdict(list)
    for row in rows:
        grouped[(row.qualification_code, row.duration_weeks)].append(row)
    summaries = []
    for (code, duration), group in sorted(grouped.items()):
        summaries.append(
            QualificationSummary(
                qualification_code=code,
                duration_weeks=duration,
                training_package=package_of(code),
                row_count=len(group),
                intake_count=len({item.intake_label for item in group}),
            )
        )
    return summaries


def _as_dict(summary: QualificationSummary) -> dict:
    return {
        "qualification_code": summary.qualification_code,
        "duration_weeks": summary.duration_weeks,
        "training_package": summary.training_package,
        "row_count": summary.row_count,
        "intake_count": summary.intake_count,
    }


def validate_bytes(
    session: Session,
    *,
    training_package: str,
    file_name: str,
    payload: bytes,
) -> tuple[ImportReview, list[ParsedRow]]:
    package = training_package.upper().strip()
    if package not in TRAINING_PACKAGE_VALUES:
        raise RollingImportError("Choose exactly one of the eleven approved training packages.")

    issues: list[Discrepancy] = []
    headers, body = _read_tabular(file_name, payload)
    columns = _map_headers(headers, issues)
    parsed: list[ParsedRow] = []
    if columns is not None:
        parsed = _parse_body(body, columns, issues)
        parsed = _assign_slots_and_dedupe(parsed, issues)
        _stamp_delivery_spans(parsed)
        _assert_week_calendar(parsed, issues)

    matching = [row for row in parsed if package_of(row.qualification_code) == package]
    other = [row for row in parsed if package_of(row.qualification_code) != package]

    if not matching:
        issues.append(
            Discrepancy(
                KIND_EMPTY_FOR_PACKAGE,
                "refuse",
                None,
                None,
                package,
                "The file is empty, or contains no row for the selected training package.",
            )
        )

    other_by_qual = _summaries(other)
    for summary in other_by_qual:
        issues.append(
            Discrepancy(
                KIND_PACKAGE_MISMATCH,
                "choose",
                None,
                "qualification_code",
                summary.qualification_code,
                f"{summary.qualification_code} belongs to {summary.training_package}, not {package} ({summary.row_count} rows).",
            )
        )

    approved_units = {code for (code,) in session.execute(select(Unit.unit_code)).all()}
    unknown_counts: dict[str, int] = defaultdict(int)
    for row in matching:
        if row.schedule_type != TYPE_UNIT or not row.unit_code:
            continue
        stored = row.unit_code
        members = [part.strip() for part in stored.split("/") if part.strip()]
        known = stored in approved_units or (len(members) > 1 and all(part in approved_units for part in members))
        if not known:
            unknown_counts[stored] += 1
    for code, count in sorted(unknown_counts.items()):
        issues.append(
            Discrepancy(
                KIND_UNKNOWN_UNIT,
                "warn",
                None,
                "unit_code",
                code,
                f"{code} is not in the approved units table ({count} rows). The timetable is still stored.",
            )
        )

    existing = list(
        session.execute(
            select(
                RollingTimetableWeek.qualification_code,
                RollingTimetableWeek.duration_weeks,
            )
            .where(RollingTimetableWeek.training_package == package)
            .distinct()
        ).all()
    )
    existing_by_code = {code: duration for code, duration in existing}
    replaced: list[str] = []
    for summary in _summaries(matching):
        stored_duration = existing_by_code.get(summary.qualification_code)
        if stored_duration is None:
            continue
        replaced.append(summary.qualification_code)
        if stored_duration != summary.duration_weeks:
            issues.append(
                Discrepancy(
                    KIND_DURATION_ALREADY_STORED,
                    "warn",
                    None,
                    "duration_weeks",
                    str(summary.duration_weeks),
                    f"{summary.qualification_code} is already stored under {stored_duration} weeks.",
                )
            )

    by_intake: dict[str, list[ParsedRow]] = defaultdict(list)
    for row in matching:
        by_intake[row.intake_label].append(row)
    span_mismatches = 0
    for label, group in by_intake.items():
        if not any(item.schedule_type == TYPE_UNIT for item in group):
            issues.append(
                Discrepancy(
                    KIND_INTAKE_WITHOUT_UNIT,
                    "warn",
                    group[0].source_row,
                    "intake_label",
                    label,
                    f"{label} contains no UNIT row.",
                )
            )
        first = min(item.week_no for item in group)
        last = max(item.week_no for item in group)
        span = last - first + 1
        duration = group[0].duration_weeks
        if span != duration:
            span_mismatches += 1
    if span_mismatches:
        issues.append(
            Discrepancy(
                KIND_DURATION_SPAN,
                "warn",
                None,
                "duration_weeks",
                str(span_mismatches),
                f"{span_mismatches} intake(s) deliver over a span that disagrees with duration_weeks.",
            )
        )

    refused = any(item.kind in REFUSE_KINDS for item in issues)
    mixed = bool(other) and bool(matching) and not refused
    status = "refused" if refused else ("mixed" if mixed else "accepted")
    counts = {
        TYPE_UNIT: sum(1 for row in matching if row.schedule_type == TYPE_UNIT),
        TYPE_BREAK: sum(1 for row in matching if row.schedule_type == TYPE_BREAK),
        TYPE_ASSESSMENT: sum(1 for row in matching if row.schedule_type == TYPE_ASSESSMENT),
    }
    review = ImportReview(
        status=status,
        training_package=package,
        file_name=file_name,
        rows_read=len(parsed),
        rows_that_would_be_written=0 if refused else len(matching),
        qualifications=_summaries(parsed),
        matching_qualifications=_summaries(matching),
        non_matching_qualifications=_summaries(other),
        counts=counts,
        discrepancies=issues,
        existing_qualifications_replaced=replaced,
        refused=refused,
        can_proceed_with_package=mixed,
    )
    return review, matching


def review_to_dict(review: ImportReview) -> dict:
    return {
        "status": review.status,
        "training_package": review.training_package,
        "file_name": review.file_name,
        "rows_read": review.rows_read,
        "rows_that_would_be_written": review.rows_that_would_be_written,
        "qualifications": [_as_dict(item) for item in review.qualifications],
        "matching_qualifications": [_as_dict(item) for item in review.matching_qualifications],
        "non_matching_qualifications": [_as_dict(item) for item in review.non_matching_qualifications],
        "counts": {
            "unit": review.counts.get(TYPE_UNIT, 0),
            "break_count": review.counts.get(TYPE_BREAK, 0),
            "assessment_week": review.counts.get(TYPE_ASSESSMENT, 0),
        },
        "discrepancies": [
            {
                "kind": item.kind,
                "severity": item.severity,
                "row_number": item.row_number,
                "column": item.column,
                "value": item.value,
                "message": item.message,
            }
            for item in review.discrepancies
        ],
        "discrepancies_by_kind": {
            kind: [
                {
                    "kind": item.kind,
                    "severity": item.severity,
                    "row_number": item.row_number,
                    "column": item.column,
                    "value": item.value,
                    "message": item.message,
                }
                for item in items
            ]
            for kind, items in review.grouped_discrepancies().items()
        },
        "existing_qualifications_replaced": review.existing_qualifications_replaced,
        "refused": review.refused,
        "can_proceed_with_package": review.can_proceed_with_package,
    }


def apply_rows(
    session: Session,
    *,
    training_package: str,
    file_name: str,
    payload: bytes,
    proceed_with_matching: bool,
    user: User | None,
) -> ImportApplyResult:
    review, matching = validate_bytes(
        session, training_package=training_package, file_name=file_name, payload=payload
    )
    if review.refused:
        raise RollingImportError("The file was refused. Nothing was written.")
    if review.can_proceed_with_package and not proceed_with_matching:
        raise RollingImportError("The file spans more than one training package. Choose Proceed or Discard.")

    package = review.training_package
    loops = {(row.qualification_code, row.duration_weeks) for row in matching}
    for code, duration in loops:
        session.execute(
            delete(RollingTimetableWeek).where(
                RollingTimetableWeek.training_package == package,
                RollingTimetableWeek.qualification_code == code,
                RollingTimetableWeek.duration_weeks == duration,
            )
        )
    mappings = [row.as_mapping(package) for row in matching]
    if mappings:
        session.execute(insert(RollingTimetableWeek), mappings)
        session.flush()

    from app.services.allocation_import import _raise_or_count_suggestion, _upsert_suggestions

    approved_units = {code for (code,) in session.execute(select(Unit.unit_code)).all()}
    unit_suggestions: dict[tuple, dict] = {}
    for row in matching:
        if row.schedule_type != TYPE_UNIT or not row.unit_code:
            continue
        stored = row.unit_code
        members = [part.strip() for part in stored.split("/") if part.strip()]
        known = stored in approved_units or (len(members) > 1 and all(part in approved_units for part in members))
        if known:
            continue
        _raise_or_count_suggestion(unit_suggestions, "UNIT", stored, {"training_package": package})
    if unit_suggestions:
        _upsert_suggestions(session, unit_suggestions, dt.datetime.now(dt.timezone.utc))

    skipped = [item.qualification_code for item in review.non_matching_qualifications]
    replaced = sorted({code for code, _duration in loops})
    kind_counts = defaultdict(int)
    for item in review.discrepancies:
        kind_counts[item.kind] += 1
    detail = (
        f"Imported {file_name} under {package}: read {review.rows_read}, "
        f"wrote {len(mappings)}, replaced {', '.join(replaced) or 'none'}, "
        f"skipped {', '.join(skipped) or 'none'}. Discrepancies: {dict(kind_counts) or 'none'}."
    )
    record_activity(
        session,
        user=user,
        action="IMPORT",
        page_or_function="Page 1 - Timetable View and Management",
        detail=detail,
        record_reference=f"{package}:{file_name}:{len(mappings)}",
        result="COMPLETED",
        user_reference=None if user else "Command-line import",
    )
    return ImportApplyResult(
        rows_written=len(mappings),
        qualifications_replaced=replaced,
        qualifications_skipped=skipped,
        rows_read=review.rows_read,
    )


def export_flat(rows: Iterable[RollingTimetableWeek]) -> tuple[list[str], list[list[str]]]:
    body: list[list[str]] = []
    for row in rows:
        body.append(
            [
                row.qualification_code,
                str(row.duration_weeks),
                row.intake_label,
                row.intake_group,
                row.intake_start_date.isoformat(),
                str(row.week_no),
                row.week_start_date.isoformat(),
                row.week_end_date.isoformat(),
                row.schedule_type,
                row.schedule_value,
                row.unit_code or "",
                str(row.unit_count),
                "" if row.unit_delivery_span_weeks is None else str(row.unit_delivery_span_weeks),
            ]
        )
    return list(FLAT_COLUMNS), body
