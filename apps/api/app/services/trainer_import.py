"""Trainer bulk import — Trainer Location and Details, and Trainer Units.

**Which kind of data, not which training package** (1.7). A trainer is not tied
to one package: the real BSB workbook contains a trainer who teaches only FNS
qualifications. The two accepted shapes are `LOCATION` and `UNITS`, and the
choice selects the column map.

**What each issue offers** (approved 15 September 2026, replacing 1.8). A value
that matches no approved record - a campus, a qualification, a unit, a unit its
qualification does not list, a city the City Dictionary does not hold - is
raised as a suggestion, never accepted as an exception. A predefined rule broken
by a row that can still be stored - the file's city disagreeing with the city
its campus is in - is accepted as an exception for this import only. A value
that cannot be stored is corrected, or its row excluded.

**Reuses the Schema v1 staging stack** — `import_batches`, `import_staged_rows`,
`import_row_issues` — rather than adding a third. A trainer row's working values
live in `import_staged_rows.working_values`, because the typed `*_value` columns
model a student row.

**Flat query counts.** Every lookup is loaded once before the loop and every
write is a bulk insert. A 363-row units file must not issue 363 inserts, and
`test_trainer_import.py` pins that.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from uuid import uuid4
from collections import defaultdict

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.models.allocation import ReferenceSuggestion
from app.models.college import Campus, City
from app.models.import_batch import ImportBatch, ImportRowIssue, ImportStagedRow
from app.models.qualification import Qualification, QualificationUnit, Unit
from app.models.trainer import Trainer, TrainerAvailability, TrainerUnit
from app.models.user import User
from app.services.activity import record_activity
from app.services.reference_suggestions import merge_attributes, raise_reference_suggestion
from app.services.trainers import rebuild_trainer_qualifications

PAGE = "Page 3 - Trainer Data"
SOURCE = "TRAINER_IMPORT"

#: The two shapes the import accepts (1.7). Never a training package.
DATA_TYPES = ("LOCATION", "UNITS")

#: The sheet each shape lives on in the supplied workbook. A single-sheet file
#: falls back to the first worksheet, so a CSV export of one sheet still works.
SHEET_NAMES = {"LOCATION": "trainer location", "UNITS": "trainer units"}

LOCATION_HEADERS = {
    "sl no.": "sl_no",
    "sl no": "sl_no",
    "trainer id": "trainer_id",
    "trainer name": "trainer_name",
    "trainer campus": "trainer_campus",
    "location": "location",
    "location type": "location_type",
    "working time": "working_time",
    "delivery type": "delivery_type",
    "monday": "monday",
    "tuesday": "tuesday",
    "wednesday": "wednesday",
    "thursday": "thursday",
    "friday": "friday",
}
UNITS_HEADERS = {
    "trainer id": "trainer_id",
    "qualifications they can teach": "qualification_code",
    "qualification": "qualification_code",
    "units they can teach": "unit_code",
    "unit": "unit_code",
}

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")

_TIME = re.compile(r"^\s*(\d{1,2})(?::(\d{2}))?\s*([AaPp])\.?[Mm]\.?")


class TrainerImportError(ValueError):
    """A refusal the route turns into a 4xx."""


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


#: Zero-width characters carry no meaning in a code and are invisible on
#: screen, so a cell that reads `FNSACC601` can fail to match an approved unit
#: for a reason nobody can see. The real source file contains exactly that: two
#: U+200B before `FNSACC601`. Stripping them is normalisation, not a guess —
#: `\s` does not match them, so `strip()` alone leaves them in place.
_INVISIBLE = str.maketrans({c: None for c in "​‌‍⁠﻿"})


def _norm(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).translate(_INVISIBLE)).strip()


def _key(value: object) -> str:
    return _norm(value).upper()


def _read_tabular(file_name: str, payload: bytes, data_type: str) -> tuple[list, list[list]]:
    """(header cells, data rows) from a CSV or XLSX upload.

    The supplied workbook holds both shapes on separate sheets, so the sheet is
    chosen by the data type the user picked rather than always taking the first.
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
            wanted = SHEET_NAMES[data_type]
            sheet = None
            for candidate in workbook.worksheets:
                if _norm(candidate.title).lower() == wanted:
                    sheet = candidate
                    break
            if sheet is None:
                sheet = workbook.worksheets[0]
            values = list(sheet.iter_rows(values_only=True))
        finally:
            workbook.close()
        if not values:
            return [], []
        return list(values[0]), [list(r) for r in values[1:]]
    raise TrainerImportError("The file must be a CSV or XLSX workbook.")


def _map_headers(cells: list, data_type: str) -> dict[str, int]:
    aliases = LOCATION_HEADERS if data_type == "LOCATION" else UNITS_HEADERS
    columns: dict[str, int] = {}
    for index, cell in enumerate(cells):
        canonical = aliases.get(_norm(cell).lower())
        if canonical and canonical not in columns:
            columns[canonical] = index
    required = (
        ("trainer_id", "trainer_name", "location", "working_time")
        if data_type == "LOCATION"
        else ("trainer_id", "qualification_code", "unit_code")
    )
    missing = [name for name in required if name not in columns]
    if missing:
        raise TrainerImportError(
            "The file is missing required column(s): " + ", ".join(sorted(missing)) + "."
        )
    return columns


def parse_working_time(raw: str) -> tuple[dt.time, dt.time] | None:
    """`9:00 AM to 5:00 PM AEST/AEDT` -> (09:00, 17:00).

    Any trailing timezone text is deliberately not interpreted — it is kept
    verbatim in `working_time_text`. A window that cannot be read returns None
    and becomes a blocking row issue naming the cell; it is never guessed at and
    never defaulted (check A6).
    """
    text = _norm(raw)
    if not text:
        return None
    parts = re.split(r"\bto\b|[-–—]", text, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) != 2:
        return None
    times = []
    for part in parts:
        match = _TIME.match(part)
        if not match:
            return None
        hour = int(match.group(1))
        minute = int(match.group(2) or 0)
        meridian = match.group(3).upper()
        if not (1 <= hour <= 12) or minute > 59:
            return None
        if meridian == "A":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
        times.append(dt.time(hour, minute))
    if times[1] <= times[0]:
        return None
    return times[0], times[1]


def parse_weekday_mode(raw: str) -> str:
    """`Physical` / `Virtual` / `NA` or blank -> the stored per-day mode."""
    value = _key(raw)
    if value in {"PHYSICAL", "P", "F2F", "FACE TO FACE"}:
        return "PHYSICAL"
    if value in {"VIRTUAL", "V", "ONLINE"}:
        return "VIRTUAL"
    return "NOT_AVAILABLE"


def parse_class_type(raw: str) -> str | None:
    value = _key(raw).replace("&", "AND")
    if value in {"THEORY AND PRACTICAL", "THEORY_AND_PRACTICAL", "BOTH"}:
        return "THEORY_AND_PRACTICAL"
    if value in {"THEORY", "THEORY ONLY"}:
        return "THEORY"
    if value in {"PRACTICAL", "PRACTICAL ONLY"}:
        return "PRACTICAL"
    if not value:
        return "THEORY"
    return None


# ---------------------------------------------------------------------------
# Lookups — loaded once, never per row
# ---------------------------------------------------------------------------


class _Lookups:
    def __init__(self, session: Session):
        self.trainers: dict[str, int] = {}
        self.trainer_names: dict[str, str] = {}
        for pk, code, name in session.execute(
            select(Trainer.id, Trainer.trainer_id, Trainer.trainer_name).where(
                Trainer.is_deleted.is_(False)
            )
        ).all():
            self.trainers[_key(code)] = pk
            self.trainer_names[_key(code)] = name

        self.campuses: dict[str, int] = {}
        self.campus_city: dict[int, str | None] = {}
        for pk, code, name, location, city in session.execute(
            select(Campus.id, Campus.campus_code, Campus.campus_name, Campus.campus_location, Campus.city)
        ).all():
            self.campus_city[pk] = city
            # Resolved against code, name and location, case-insensitively.
            for alias in (code, name, location):
                if alias:
                    self.campuses.setdefault(_key(alias), pk)

        #: The City Dictionary: normalised name -> the name as recorded.
        self.cities: dict[str, str] = {
            _key(name): name for (name,) in session.execute(select(City.city_name)).all()
        }

        self.qualifications: dict[str, int] = {}
        for pk, code in session.execute(
            select(Qualification.id, Qualification.qualification_code).where(
                Qualification.qualification_code.is_not(None)
            )
        ).all():
            self.qualifications.setdefault(_key(code), pk)

        self.units: dict[str, int] = {}
        for pk, code in session.execute(select(Unit.id, Unit.unit_code)).all():
            self.units.setdefault(_key(code), pk)

        #: What is already stored for each trainer/place/class/start, so a
        #: re-import can tell a genuinely new row from a changed one.
        self.availability: dict[tuple, dict] = {}
        for row in session.execute(select(TrainerAvailability)).scalars():
            key = (
                row.trainer_id,
                row.campus_id,
                _key(row.location_text),
                row.class_type,
                row.working_time_start,
            )
            self.availability[key] = {
                "id": row.id,
                "monday": row.monday,
                "tuesday": row.tuesday,
                "wednesday": row.wednesday,
                "thursday": row.thursday,
                "friday": row.friday,
                "working_time_end": row.working_time_end.isoformat(),
                "working_time_text": row.working_time_text,
                "location_type": row.location_type,
            }

        self.membership: set[tuple[int, int]] = {
            (row.qualification_id, row.unit_id)
            for row in session.execute(
                select(QualificationUnit.qualification_id, QualificationUnit.unit_id).where(
                    QualificationUnit.is_deleted.is_(False)
                )
            ).all()
        }


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _issue(field: str, message: str, severity: str) -> dict:
    return {"field_name": field, "message": message, "issue_status": severity}


def _check_city(
    values: dict, resolved: dict, lookups: _Lookups, raised: set[str], issues: list[dict]
) -> None:
    """The file's Trainer Campus, checked against the City Dictionary (15 September 2026).

    * A city the dictionary does not hold is an unmatched value: a CITY
      suggestion, raised like any other. Raised, the row imports with the city
      as written, and adding or mapping the city closes the entry.
    * A city the dictionary holds that disagrees with the city the row's campus
      is in breaks a rule: an exception, accepted for this import only.
    * Offshore is not a city, and a campus with no city recorded has nothing to
      disagree with.

    `resolved["city"]` is what the trainer's city is stored as: the dictionary's
    spelling when it holds the city, the file's otherwise.
    """
    declared = _norm(values.get("trainer_campus"))
    resolved["city"] = None
    if not declared or _key(declared) == "OFFSHORE" or resolved.get("is_offshore"):
        return

    known = lookups.cities.get(_key(declared))
    if known is None:
        resolved["city"] = declared
        if _unresolved_key("CITY", declared, {}) in raised:
            issues.append(
                _issue(
                    "Trainer Campus",
                    f"'{declared}' has been raised as a suggestion. Stored as written until the "
                    "city is added to the City Dictionary or mapped.",
                    "RAISED",
                )
            )
        else:
            issues.append(
                _issue(
                    "Trainer Campus",
                    f"'{declared}' is not in the City Dictionary. Add the city, or map it to one "
                    "that is.",
                    "UNRESOLVED",
                )
            )
        return

    resolved["city"] = known
    campus_id = resolved.get("campus_id")
    recorded = lookups.campus_city.get(campus_id) if campus_id else None
    if recorded and _key(recorded) != _key(known):
        location = _norm(values.get("location"))
        if values.get("_accepted_exception"):
            issues.append(
                _issue(
                    "Trainer Campus",
                    f"The file says '{known}' but {location} is in '{recorded}'. Accepted as an "
                    "exception for this import.",
                    "ACCEPTED",
                )
            )
        else:
            issues.append(
                _issue(
                    "Trainer Campus",
                    f"The file says '{known}' but {location} is in '{recorded}'. Correct the file, "
                    "or accept it as an exception for this import.",
                    "EXCEPTION",
                )
            )


def _validate_location(values: dict, lookups: _Lookups, raised: set[str]) -> tuple[list[dict], dict]:
    issues: list[dict] = []
    resolved: dict = {}

    if not values.get("trainer_id"):
        issues.append(_issue("Trainer id", "A trainer id is required.", "ERROR"))
    if not values.get("trainer_name"):
        issues.append(_issue("Trainer name", "A trainer name is required.", "ERROR"))

    # `SL No.` is a row number, not data — the same treatment the student
    # importer gives the `Group` column.
    if values.get("sl_no"):
        issues.append(
            _issue("SL No.", "Ignored — a row number in the file, not stored data.", "NOTE")
        )

    location = _norm(values.get("location"))
    if _key(location) == "OFFSHORE":
        # A valid state, not an unresolved one: no suggestion is raised (1.3).
        resolved["is_offshore"] = True
        resolved["campus_id"] = None
        resolved["location_text"] = "Offshore"
    elif not location:
        issues.append(_issue("Location", "A location is required.", "ERROR"))
    else:
        campus_id = lookups.campuses.get(_key(location))
        resolved["is_offshore"] = False
        if campus_id is None:
            resolved["campus_id"] = None
            resolved["location_text"] = location
            if _unresolved_key("CAMPUS", location, {}) in raised:
                # Raised: the row imports and keeps the raw value, exactly as the
                # allocation import behaves. Resolving the suggestion repairs it.
                issues.append(
                    _issue(
                        "Location",
                        f"'{location}' has been raised as a suggestion. Stored as written "
                        "until an approved campus is created or mapped.",
                        "RAISED",
                    )
                )
            else:
                issues.append(
                    _issue(
                        "Location",
                        f"'{location}' does not match an approved campus. "
                        "Create the campus or map it to an existing one.",
                        "UNRESOLVED",
                    )
                )
        else:
            resolved["campus_id"] = campus_id
            resolved["location_text"] = None

    _check_city(values, resolved, lookups, raised, issues)

    window = parse_working_time(values.get("working_time", ""))
    if window is None:
        issues.append(
            _issue(
                "Working Time",
                f"'{_norm(values.get('working_time'))}' could not be read as a time window.",
                "ERROR",
            )
        )
    else:
        resolved["working_time_start"], resolved["working_time_end"] = window
        resolved["working_time_text"] = _norm(values.get("working_time"))

    class_type = parse_class_type(values.get("delivery_type", ""))
    if class_type is None:
        issues.append(
            _issue(
                "Delivery Type",
                f"'{_norm(values.get('delivery_type'))}' is not Theory, Practical, "
                "or Theory and Practical.",
                "ERROR",
            )
        )
    else:
        resolved["class_type"] = class_type

    for day in WEEKDAYS:
        resolved[day] = parse_weekday_mode(values.get(day, ""))
    resolved["location_type"] = _norm(values.get("location_type")) or None
    return issues, resolved


def _validate_units(values: dict, lookups: _Lookups, raised: set[str]) -> tuple[list[dict], dict]:
    issues: list[dict] = []
    resolved: dict = {}

    code = _norm(values.get("trainer_id"))
    if not code:
        issues.append(_issue("Trainer ID", "A trainer id is required.", "ERROR"))
    else:
        trainer_pk = lookups.trainers.get(_key(code))
        resolved["trainer_pk"] = trainer_pk
        if trainer_pk is None:
            # 1.9: flagged and grouped, never created from a units file, and the
            # rest of the file can still be imported.
            issues.append(
                _issue(
                    "Trainer ID",
                    f"'{code}' is not in the trainer database. "
                    "Import the Trainer Location and Details file first.",
                    "UNMATCHED",
                )
            )

    qual = _norm(values.get("qualification_code"))
    qualification_pk = lookups.qualifications.get(_key(qual)) if qual else None
    resolved["qualification_pk"] = qualification_pk
    resolved["qualification_text"] = None if qualification_pk else (qual or None)
    if not qual:
        issues.append(_issue("Qualifications They Can Teach", "A qualification is required.", "ERROR"))
    elif qualification_pk is None:
        # Raised: the row imports and keeps the raw value, the way the
        # allocation import already behaves. Resolving the suggestion repairs it.
        raised_here = _unresolved_key("QUALIFICATION", qual, {}) in raised
        issues.append(
            _issue(
                "Qualifications They Can Teach",
                f"'{qual}' has been raised as a suggestion. Stored as written until an "
                "approved qualification is created or mapped."
                if raised_here
                else f"'{qual}' does not match an approved qualification. Create it or map it.",
                "RAISED" if raised_here else "UNRESOLVED",
            )
        )

    unit = _norm(values.get("unit_code"))
    unit_pk = lookups.units.get(_key(unit)) if unit else None
    resolved["unit_pk"] = unit_pk
    resolved["unit_text"] = None if unit_pk else (unit or None)
    if not unit:
        issues.append(_issue("Units They Can Teach", "A unit is required.", "ERROR"))
    elif unit_pk is None:
        raised_here = _unresolved_key("UNIT", unit, {"qualification": qual}) in raised
        issues.append(
            _issue(
                "Units They Can Teach",
                f"'{unit}' has been raised as a suggestion. Stored as written until an "
                "approved unit is created or mapped."
                if raised_here
                else f"'{unit}' does not match an approved unit. Create it or map it.",
                "RAISED" if raised_here else "UNRESOLVED",
            )
        )

    # A unit its qualification does not list is an unmatched value (15 September
    # 2026, replacing check B6's warning): the same membership gap a rolling
    # timetable raises, raised the same way. Raised, the row imports as given, and
    # adding the unit to the qualification closes the entry.
    if qualification_pk and unit_pk and (qualification_pk, unit_pk) not in lookups.membership:
        raised_here = _unresolved_key("UNIT", unit, {"qualification": qual}) in raised
        issues.append(
            _issue(
                "Units They Can Teach",
                f"'{unit}' is not listed under {qual}. It has been raised as a suggestion and is "
                "stored as given until it is added to the qualification."
                if raised_here
                else f"'{unit}' is not listed under {qual}. Raise a suggestion to add it to the "
                "qualification.",
                "RAISED" if raised_here else "UNRESOLVED",
            )
        )
    return issues, resolved


#: Fields a re-import can change on a location that is already stored. The
#: place, class type and start time are the row's identity, so a change to any
#: of those is a new row rather than an override.
_OVERRIDABLE = (
    ("monday", "Monday"),
    ("tuesday", "Tuesday"),
    ("wednesday", "Wednesday"),
    ("thursday", "Thursday"),
    ("friday", "Friday"),
    ("working_time_end", "Working time (end)"),
    ("working_time_text", "Working time"),
    ("location_type", "Location Type"),
)


def _detect_override(values: dict, resolved: dict, lookups: _Lookups) -> list[dict]:
    """What this row would change on a location already stored.

    Approved 27 August 2026: adding is silent, **overwriting is not**. A file
    that quietly changed which days a trainer works at a campus would be a
    change nobody saw, so each one is listed with its stored and incoming value
    and waits for a decision.
    """
    trainer_pk = lookups.trainers.get(_key(values.get("trainer_id")))
    start = resolved.get("working_time_start")
    if not trainer_pk or not start:
        return []
    stored = lookups.availability.get(
        (
            trainer_pk,
            resolved.get("campus_id"),
            _key(resolved.get("location_text")),
            resolved.get("class_type", "THEORY"),
            dt.time.fromisoformat(start) if isinstance(start, str) else start,
        )
    )
    if stored is None:
        return []

    changes = []
    for field, label in _OVERRIDABLE:
        incoming = resolved.get(field)
        held = stored.get(field)
        if field == "working_time_end" and incoming is not None:
            incoming = incoming if isinstance(incoming, str) else incoming.isoformat()
        if (incoming or None) != (held or None):
            changes.append(
                {
                    "field": field,
                    "label": label,
                    "stored_value": str(held) if held is not None else "",
                    "incoming_value": str(incoming) if incoming is not None else "",
                }
            )
    return changes


def _status_for(issues: list[dict], duplicate: bool) -> str:
    codes = {i["issue_status"] for i in issues}
    if duplicate:
        return "DUPLICATE"
    if "UNMATCHED" in codes:
        return "UNMATCHED_REFERENCE"
    if "ERROR" in codes or "UNRESOLVED" in codes or "EXCEPTION" in codes:
        return "NEEDS_CORRECTION"
    return "READY"


# ---------------------------------------------------------------------------
# Stage
# ---------------------------------------------------------------------------


def stage_file(
    session: Session, *, data_type: str, file_name: str, payload: bytes, user: User
) -> dict:
    if data_type not in DATA_TYPES:
        raise TrainerImportError("Choose Trainer Location and Details, or Trainer Units.")

    header, body = _read_tabular(file_name, payload, data_type)
    columns = _map_headers(header, data_type)
    lookups = _Lookups(session)

    batch = ImportBatch(
        batch_reference=f"TRN-{data_type}-{uuid4().hex}",
        file_name=file_name,
        file_size_bytes=len(payload),
        uploaded_at=dt.datetime.now(dt.timezone.utc),
        uploaded_by_user_id=user.id,
        row_count=0,
        status="STAGED",
        data_type=data_type,
    )
    session.add(batch)
    session.flush()
    batch.batch_reference = f"TRN-{data_type}-{batch.id}"

    seen: set[tuple] = set()
    staged: list[ImportStagedRow] = []
    issues_by_index: list[list[dict]] = []

    for offset, cells in enumerate(body):
        values = {
            name: _norm(cells[index]) if index < len(cells) else ""
            for name, index in columns.items()
        }
        if not any(values.values()):
            continue

        if data_type == "LOCATION":
            issues, resolved = _validate_location(values, lookups, set())
            overrides = _detect_override(values, _jsonable(resolved), lookups)
            natural = (_key(values.get("trainer_id")), _key(values.get("location")))
        else:
            overrides = []
            issues, resolved = _validate_units(values, lookups, set())
            # (Trainer, Qualification, Unit) — the same unit under two
            # qualifications is the normal case, not a duplicate (2.13.2).
            natural = (
                _key(values.get("trainer_id")),
                _key(values.get("qualification_code")),
                _key(values.get("unit_code")),
            )

        duplicate = natural in seen
        if duplicate:
            issues.append(
                _issue("Row", "This row repeats an earlier row in the file.", "DUPLICATE")
            )
        seen.add(natural)

        row = ImportStagedRow(
            import_batch_id=batch.id,
            source_row_number=offset + 2,
            raw_values=values,
            working_values={
                **values,
                "_resolved": _jsonable(resolved),
                "_override": overrides,
            },
            status=_status_for(issues, duplicate),
            duplicate_detected=duplicate,
        )
        staged.append(row)
        issues_by_index.append(issues)

    session.add_all(staged)
    session.flush()

    session.add_all(
        [
            ImportRowIssue(
                import_staged_row_id=row.id,
                field_name=issue["field_name"],
                message=issue["message"],
                issue_status=issue["issue_status"],
            )
            for row, issues in zip(staged, issues_by_index)
            for issue in issues
        ]
    )
    batch.row_count = len(staged)
    session.flush()

    record_activity(
        session,
        user=user,
        action="CREATE",
        page_or_function=PAGE,
        detail=(
            f"Staged {len(staged)} row(s) from '{file_name}' for the "
            f"{'Trainer Location and Details' if data_type == 'LOCATION' else 'Trainer Units'} import."
        ),
        record_reference=str(batch.id),
        result="COMPLETED",
    )
    return read_batch(session, batch.id)


def _jsonable(resolved: dict) -> dict:
    out = {}
    for key, value in resolved.items():
        out[key] = value.isoformat() if isinstance(value, dt.time) else value
    return out


def _unresolved_key(entity: str, raw: str, context: dict) -> str:
    """A stable handle for one unmatched value, used by the review and the
    Raise action so the client never has to reconstruct the context."""
    return f"{entity}|{_key(raw)}|{json.dumps(context, sort_keys=True)}"


def collect_unresolved(session: Session, batch_id: int) -> list[dict]:
    """The distinct values in this batch that match no approved record.

    **Detected, not written.** Raising is the user's decision (a value they
    recognise as a typo is corrected, not added to the reference data), so this
    only reports. `in_queue` says whether an entry already exists — the queue
    holds one entry per value however many imports flagged it.

    A `UNIT` is scoped by its qualification; a `CAMPUS` by nothing, because the
    trainer file carries no college. There is **no exception path**: a unit
    either exists in the reference data or it does not (1.8).
    """
    rows = session.execute(
        select(ImportStagedRow)
        .where(ImportStagedRow.import_batch_id == batch_id)
        .order_by(ImportStagedRow.source_row_number)
    ).scalars().all()
    issues = defaultdict(list)
    for issue in session.execute(
        select(ImportRowIssue).where(
            ImportRowIssue.import_staged_row_id.in_([r.id for r in rows] or [0])
        )
    ).scalars():
        issues[issue.import_staged_row_id].append(issue)

    wanted: dict[str, dict] = {}
    for row in rows:
        if row.excluded_by_user:
            continue
        values = {k: v for k, v in (row.working_values or {}).items() if k != "_resolved"}
        for issue in issues.get(row.id, []):
            if issue.issue_status not in {"UNRESOLVED", "RAISED"}:
                continue
            attributes: dict = {}
            if issue.field_name == "Location":
                entity, raw, context = "CAMPUS", _norm(values.get("location")), {}
            elif issue.field_name == "Trainer Campus":
                entity, raw, context = "CITY", _norm(values.get("trainer_campus")), {}
                # The campuses the city was named for, so the dictionary form can
                # arrive with them chosen.
                location = _norm(values.get("location"))
                attributes = {"campuses": [location]} if location else {}
            elif issue.field_name == "Qualifications They Can Teach":
                entity, raw, context = "QUALIFICATION", _norm(values.get("qualification_code")), {}
            else:
                entity = "UNIT"
                raw = _norm(values.get("unit_code"))
                context = {"qualification": _norm(values.get("qualification_code"))}
            if not raw:
                continue
            key = _unresolved_key(entity, raw, context)
            entry = wanted.setdefault(
                key,
                {
                    "key": key,
                    "entity_type": entity,
                    "raw_value": raw,
                    "context": context,
                    "row_count": 0,
                    "in_queue": False,
                    "queue_status": None,
                    "raised_here": False,
                    "attributes": {},
                },
            )
            entry["row_count"] += 1
            entry["attributes"] = merge_attributes(entry["attributes"], attributes)

    raised_here = _raised_keys(rows)
    for entry in wanted.values():
        entry["raised_here"] = entry["key"] in raised_here

    if not wanted:
        return []

    # One query for the whole set, never one per value.
    held = {
        (row.entity_type, row.normalised_value, row.context_key): row.status
        for row in session.execute(
            select(ReferenceSuggestion).where(
                ReferenceSuggestion.entity_type.in_({e["entity_type"] for e in wanted.values()})
            )
        ).scalars()
    }
    for entry in wanted.values():
        status = held.get(
            (
                entry["entity_type"],
                _key(entry["raw_value"]),
                json.dumps(entry["context"], sort_keys=True),
            )
        )
        entry["in_queue"] = status is not None
        entry["queue_status"] = status
    return sorted(wanted.values(), key=lambda e: (e["entity_type"], e["raw_value"]))


def _raised_keys(rows: list[ImportStagedRow]) -> set[str]:
    """The values this batch was told to raise, read back from its rows.

    Stored on the rows rather than the batch because `import_batches` has no
    JSON column, and every row already carries `working_values`.
    """
    keys: set[str] = set()
    for row in rows:
        keys.update((row.working_values or {}).get("_raised") or [])
    return keys


def raise_values(session: Session, batch_id: int, *, keys: list[str], user: User) -> int:
    """Raise a suggestion for the chosen unmatched values.

    The user's explicit action, not a side effect of uploading a file. An
    abandoned review therefore leaves nothing behind unless they asked for it.
    """
    wanted = {entry["key"]: entry for entry in collect_unresolved(session, batch_id)}
    chosen = [wanted[key] for key in dict.fromkeys(keys) if key in wanted]
    raised = 0
    for entry in chosen:
        # Returns False when an entry already existed — the queue holds one entry
        # per value, so a value another import already flagged is incremented
        # rather than duplicated.
        raise_reference_suggestion(
            session,
            entity_type=entry["entity_type"],
            raw_value=entry["raw_value"],
            context=entry["context"],
            source=SOURCE,
            attributes=entry.get("attributes"),
        )
        raised += 1
        record_activity(
            session,
            user=user,
            action="CREATE",
            page_or_function=PAGE,
            detail=(
                f"Raised a suggestion for {entry['entity_type'].lower()} "
                f"'{entry['raw_value']}' from the trainer import "
                f"({entry['row_count']} row(s)). The rows import with the value stored "
                "as written until it is created or mapped."
            ),
            record_reference=str(batch_id),
            result="COMPLETED",
        )

    if chosen:
        # Record the decision on the batch, then re-validate: a raised value is
        # a warning rather than a blocker, so its rows become importable.
        rows = session.execute(
            select(ImportStagedRow).where(ImportStagedRow.import_batch_id == batch_id)
        ).scalars().all()
        marked = _raised_keys(rows) | {entry["key"] for entry in chosen}
        for row in rows:
            row.working_values = {**(row.working_values or {}), "_raised": sorted(marked)}
        session.flush()
        patch_rows(
            session,
            batch_id,
            corrections={},
            excluded_row_ids=[],
            exclude_missing_trainers=False,
            user=user,
        )
    session.flush()
    return raised


# ---------------------------------------------------------------------------
# Read and correct
# ---------------------------------------------------------------------------


def read_batch(session: Session, batch_id: int) -> dict:
    batch = session.get(ImportBatch, batch_id)
    if batch is None or batch.data_type not in DATA_TYPES:
        raise TrainerImportError("That import batch was not found.")

    rows = session.execute(
        select(ImportStagedRow)
        .where(ImportStagedRow.import_batch_id == batch_id)
        .order_by(ImportStagedRow.source_row_number)
    ).scalars().all()
    issues = defaultdict(list)
    for issue in session.execute(
        select(ImportRowIssue).where(
            ImportRowIssue.import_staged_row_id.in_([r.id for r in rows] or [0])
        )
    ).scalars():
        issues[issue.import_staged_row_id].append(issue)

    missing: dict[str, int] = defaultdict(int)
    for row in rows:
        if row.status == "UNMATCHED_REFERENCE" and not row.excluded_by_user:
            missing[_norm(row.raw_values.get("trainer_id"))] += 1

    excluded = sum(1 for r in rows if r.excluded_by_user)
    blocking = [
        r
        for r in rows
        if not r.excluded_by_user and r.status in {"NEEDS_CORRECTION", "UNMATCHED_REFERENCE"}
    ]
    valid = sum(1 for r in rows if not r.excluded_by_user and r.status == "READY")

    unresolved = collect_unresolved(session, batch_id)
    overrides = [
        {
            "row_id": row.id,
            "row_number": row.source_row_number,
            "trainer_id": _norm((row.working_values or {}).get("trainer_id")),
            "location": _norm((row.working_values or {}).get("location")),
            "decision": (row.working_values or {}).get("_override_decision"),
            "changes": (row.working_values or {}).get("_override") or [],
        }
        for row in rows
        if not row.excluded_by_user and (row.working_values or {}).get("_override")
    ]
    undecided = [entry for entry in overrides if not entry["decision"]]

    message = None
    if missing:
        message = (
            f"{len(missing)} trainer id(s) in this file are not in the trainer database — "
            f"{sum(missing.values())} row(s)."
        )
    elif undecided:
        message = (
            f"{len(undecided)} row(s) would change something already stored. "
            "Choose which value to keep for each."
        )

    return {
        "batch_id": batch.id,
        "data_type": batch.data_type,
        "file_name": batch.file_name,
        "rows_read": len(rows),
        "rows_valid": valid,
        "rows_with_errors": len(blocking),
        "rows_excluded": excluded,
        # Approved 27 August 2026: a change to something already stored waits
        # for a decision. Adding is silent; overwriting is not.
        "can_apply": not blocking and not undecided and valid > 0,
        "overrides": overrides,
        "rows": [
            {
                "id": row.id,
                "row_number": row.source_row_number,
                "status": "EXCLUDED_BY_USER" if row.excluded_by_user else row.status,
                "values": {k: v for k, v in (row.working_values or {}).items() if k != "_resolved"},
                "issues": [
                    {
                        "severity": i.issue_status,
                        "code": i.issue_status,
                        "column_name": i.field_name,
                        "message": i.message,
                    }
                    for i in issues.get(row.id, [])
                ],
            }
            for row in rows
        ],
        "missing_trainers": [
            {"trainer_id": code, "row_count": count} for code, count in sorted(missing.items())
        ],
        # Detected, not written. Raising is the user's decision (2.13.4).
        "unresolved_values": unresolved,
        "suggestions_raised": sum(1 for entry in unresolved if entry["in_queue"]),
        "blocking_message": message,
    }


def patch_rows(
    session: Session,
    batch_id: int,
    *,
    corrections: dict,
    excluded_row_ids: list[int],
    exclude_missing_trainers: bool,
    user: User,
    override_decisions: dict | None = None,
    accepted_exception_row_ids: list[int] | None = None,
    withdrawn_exception_row_ids: list[int] | None = None,
    included_row_ids: list[int] | None = None,
) -> dict:
    """Apply corrections and decisions, then re-validate every row.

    Re-validation is a full pass over the batch's rows using lookups loaded
    once — never one query per row.
    """
    batch = session.get(ImportBatch, batch_id)
    if batch is None or batch.data_type not in DATA_TYPES:
        raise TrainerImportError("That import batch was not found.")

    rows = session.execute(
        select(ImportStagedRow).where(ImportStagedRow.import_batch_id == batch_id)
    ).scalars().all()
    by_id = {row.id: row for row in rows}

    for raw_id, changes in (corrections or {}).items():
        row = by_id.get(int(raw_id))
        if row is None:
            continue
        working = dict(row.working_values or {})
        working.update({k: _norm(v) for k, v in changes.items()})
        row.working_values = working
        row.corrected = True

    for raw_id, decision in (override_decisions or {}).items():
        row = by_id.get(int(raw_id))
        if row is None or decision not in {"KEEP_STORED", "TAKE_FROM_FILE"}:
            continue
        row.working_values = {**(row.working_values or {}), "_override_decision": decision}

    for row_id in excluded_row_ids or []:
        row = by_id.get(int(row_id))
        if row is not None:
            row.excluded_by_user = True

    # Undo for an exclusion.
    for row_id in included_row_ids or []:
        row = by_id.get(int(row_id))
        if row is not None:
            row.excluded_by_user = False

    # An exception accepted for this import only (15 September 2026): held on the
    # staged row, so it goes when the batch does and the next import asks again.
    for row_ids, accepted in ((accepted_exception_row_ids, True), (withdrawn_exception_row_ids, False)):
        for row_id in row_ids or []:
            row = by_id.get(int(row_id))
            if row is not None:
                row.working_values = {**(row.working_values or {}), "_accepted_exception": accepted}

    if exclude_missing_trainers:
        # 1.9: the single offered action — exclude the unmatched rows so the
        # rows for trainers that do exist can still be imported.
        for row in rows:
            if row.status == "UNMATCHED_REFERENCE":
                row.excluded_by_user = True

    lookups = _Lookups(session)
    raised = _raised_keys(rows)
    session.execute(
        delete(ImportRowIssue).where(
            ImportRowIssue.import_staged_row_id.in_([r.id for r in rows] or [0])
        )
    )
    seen: set[tuple] = set()
    fresh: list[ImportRowIssue] = []
    for row in sorted(rows, key=lambda r: r.source_row_number):
        values = {k: v for k, v in (row.working_values or {}).items() if k != "_resolved"}
        if batch.data_type == "LOCATION":
            issues, resolved = _validate_location(values, lookups, raised)
            overrides = _detect_override(values, _jsonable(resolved), lookups)
            natural = (_key(values.get("trainer_id")), _key(values.get("location")))
        else:
            overrides = []
            issues, resolved = _validate_units(values, lookups, raised)
            natural = (
                _key(values.get("trainer_id")),
                _key(values.get("qualification_code")),
                _key(values.get("unit_code")),
            )
        duplicate = natural in seen
        if duplicate:
            issues.append(
                _issue("Row", "This row repeats an earlier row in the file.", "DUPLICATE")
            )
        seen.add(natural)
        row.working_values = {
            **values,
            "_resolved": _jsonable(resolved),
            "_raised": sorted(raised),
            "_override": overrides,
            # An existing decision survives re-validation; a field that
            # is no longer being changed drops its decision with it.
            "_override_decision": (row.working_values or {}).get("_override_decision")
            if overrides
            else None,
        }
        row.duplicate_detected = duplicate
        row.status = _status_for(issues, duplicate)
        fresh.extend(
            ImportRowIssue(
                import_staged_row_id=row.id,
                field_name=i["field_name"],
                message=i["message"],
                issue_status=i["issue_status"],
            )
            for i in issues
        )
    session.add_all(fresh)
    session.flush()
    return read_batch(session, batch_id)


def abandon(session: Session, batch_id: int, *, user: User) -> None:
    batch = session.get(ImportBatch, batch_id)
    if batch is None or batch.data_type not in DATA_TYPES:
        raise TrainerImportError("That import batch was not found.")
    session.delete(batch)
    session.flush()
    record_activity(
        session,
        user=user,
        action="DELETE",
        page_or_function=PAGE,
        detail=f"Abandoned the trainer import of '{batch.file_name}'. Nothing was written.",
        record_reference=str(batch_id),
        result="COMPLETED",
    )


# ---------------------------------------------------------------------------
# Apply (2.13.5)
# ---------------------------------------------------------------------------


def apply_batch(session: Session, batch_id: int, *, apply_mode: str, user: User) -> dict:
    """Write the staged rows. One statement per table, never one per row."""
    mode = (apply_mode or "MERGE").upper()
    if mode not in {"MERGE", "REPLACE"}:
        raise TrainerImportError("The re-import mode must be Merge or Replace.")

    batch = session.get(ImportBatch, batch_id)
    if batch is None or batch.data_type not in DATA_TYPES:
        raise TrainerImportError("That import batch was not found.")

    review = read_batch(session, batch_id)
    if not review["can_apply"]:
        raise TrainerImportError(
            "Some rows still need a decision. Resolve or exclude them before confirming."
        )

    rows = session.execute(
        select(ImportStagedRow)
        .where(
            ImportStagedRow.import_batch_id == batch_id,
            ImportStagedRow.excluded_by_user.is_(False),
        )
        .order_by(ImportStagedRow.source_row_number)
    ).scalars().all()
    rows = [r for r in rows if r.status == "READY"]

    if batch.data_type == "LOCATION":
        result = _apply_locations(session, rows, mode=mode)
    else:
        result = _apply_units(session, rows, mode=mode)

    batch.status = "COMPLETED"
    batch.apply_mode = mode
    batch.completed_at = dt.datetime.now(dt.timezone.utc)
    batch.inserted_count = result["locations_written"] + result["unit_links_written"]
    batch.excluded_count = review["rows_excluded"]
    session.flush()

    label = "Trainer Location and Details" if batch.data_type == "LOCATION" else "Trainer Units"
    record_activity(
        session,
        user=user,
        action="CREATE",
        page_or_function=PAGE,
        detail=(
            f"Imported '{batch.file_name}' as {label} in {mode.title()} mode: "
            f"{result['trainers_written']} trainer(s), {result['locations_written']} location(s), "
            f"{result['unit_links_written']} unit link(s), "
            f"{result['qualification_links_written']} qualification link(s). "
            f"{review['rows_excluded']} row(s) excluded."
        ),
        record_reference=str(batch.id),
        result="COMPLETED",
    )
    return {
        "batch_id": batch.id,
        "data_type": batch.data_type,
        "apply_mode": mode,
        "rows_excluded": review["rows_excluded"],
        **result,
    }


def _apply_locations(session: Session, rows: list[ImportStagedRow], *, mode: str) -> dict:
    """Create any trainer the file names, then write their availability.

    A location file carries a name, so it *can* create a trainer. A units file
    cannot, and does not (2.13.3).
    """
    lookups = _Lookups(session)
    wanted: dict[str, str] = {}
    #: The city each trainer is based in - the file's Trainer Campus - from the
    #: first row that states one. Not stored before 15 September 2026, so a city
    #: raised as a suggestion had nothing behind it.
    cities: dict[str, str] = {}
    for row in rows:
        values = row.working_values or {}
        code = _key(values.get("trainer_id"))
        city = str((values.get("_resolved") or {}).get("city") or "").strip()
        if code and city:
            cities.setdefault(code, city)
        if code and code not in lookups.trainers:
            wanted[code] = _norm(values.get("trainer_name"))

    created = 0
    if wanted:
        session.execute(
            Trainer.__table__.insert(),
            [
                {"trainer_id": code, "trainer_name": name, "city": cities.get(code), "is_active": True}
                for code, name in wanted.items()
            ],
        )
        session.flush()
        created = len(wanted)
        for pk, code in session.execute(
            select(Trainer.id, Trainer.trainer_id).where(
                func.upper(Trainer.trainer_id).in_(list(wanted))
            )
        ).all():
            lookups.trainers[_key(code)] = pk

    # A trainer already on record takes the file's city only where none is
    # recorded: replacing one silently would be a change nobody saw. One
    # statement per distinct city, never one per trainer.
    by_city: dict[str, list[int]] = defaultdict(list)
    for code, city in cities.items():
        if code not in wanted and code in lookups.trainers:
            by_city[city].append(lookups.trainers[code])
    for city, pks in by_city.items():
        session.execute(
            update(Trainer)
            .where(Trainer.id.in_(pks), Trainer.city.is_(None))
            .values(city=city)
            .execution_options(synchronize_session=False)
        )

    trainer_pks = {
        lookups.trainers[_key((r.working_values or {}).get("trainer_id"))]
        for r in rows
        if _key((r.working_values or {}).get("trainer_id")) in lookups.trainers
    }
    if mode == "REPLACE" and trainer_pks:
        # Only the trainers named in the file, so re-uploading a corrected BSB
        # file does not delete a CHC trainer's locations.
        session.execute(
            delete(TrainerAvailability).where(TrainerAvailability.trainer_id.in_(trainer_pks))
        )
        session.flush()

    held = {
        (row.trainer_id, row.campus_id, _key(row.location_text), row.class_type, row.working_time_start)
        for row in session.execute(
            select(TrainerAvailability).where(TrainerAvailability.trainer_id.in_(trainer_pks or {0}))
        ).scalars()
    }

    payload = []
    overwritten: list[tuple] = []
    for row in rows:
        values = row.working_values or {}
        resolved = values.get("_resolved") or {}
        trainer_pk = lookups.trainers.get(_key(values.get("trainer_id")))
        if trainer_pk is None:
            continue
        start = _time(resolved.get("working_time_start"))
        end = _time(resolved.get("working_time_end"))
        if start is None or end is None:
            continue
        key = (
            trainer_pk,
            resolved.get("campus_id"),
            _key(resolved.get("location_text")),
            resolved.get("class_type", "THEORY"),
            start,
        )
        if key in held:
            # Already stored. Unchanged, or the user chose to keep what is
            # there; either way nothing is written (check A12).
            if values.get("_override_decision") != "TAKE_FROM_FILE":
                continue
            overwritten.append((key, values, resolved))
            continue
        held.add(key)
        payload.append(
            {
                "trainer_id": trainer_pk,
                "campus_id": resolved.get("campus_id"),
                "is_offshore": bool(resolved.get("is_offshore")),
                "location_text": resolved.get("location_text"),
                "location": _norm(values.get("location")) or None,
                "location_type": resolved.get("location_type"),
                "class_type": resolved.get("class_type", "THEORY"),
                "working_time_start": start,
                "working_time_end": end,
                "working_time_text": resolved.get("working_time_text"),
                **{day: resolved.get(day, "NOT_AVAILABLE") for day in WEEKDAYS},
            }
        )

    if payload:
        session.execute(TrainerAvailability.__table__.insert(), payload)
        session.flush()

    # Only the rows the user said to take from the file.
    for key, values, resolved in overwritten:
        stored = lookups.availability.get(key)
        if stored is None:
            continue
        session.execute(
            update(TrainerAvailability)
            .where(TrainerAvailability.id == stored["id"])
            .values(
                working_time_end=_time(resolved.get("working_time_end")),
                working_time_text=resolved.get("working_time_text"),
                location_type=resolved.get("location_type"),
                **{day: resolved.get(day, "NOT_AVAILABLE") for day in WEEKDAYS},
            )
        )
    if overwritten:
        session.flush()

    return {
        "locations_overwritten": len(overwritten),
        "trainers_written": created,
        "locations_written": len(payload),
        "unit_links_written": 0,
        "qualification_links_written": 0,
        "unit_links_unresolved": 0,
    }


def _apply_units(session: Session, rows: list[ImportStagedRow], *, mode: str) -> dict:
    """Write the unit links.

    A qualification or unit the reference data does not hold is stored as text
    beside a null id — the same shape `allocation_delivery` uses — so a raised
    value imports now and is repaired when its suggestion is resolved.
    """
    lookups = _Lookups(session)
    trainer_pks = set()
    links: list[dict] = []
    for row in rows:
        values = row.working_values or {}
        trainer_pk = lookups.trainers.get(_key(values.get("trainer_id")))
        # A units file never creates a trainer (2.13.3).
        if not trainer_pk:
            continue
        qual = _norm(values.get("qualification_code"))
        unit = _norm(values.get("unit_code"))
        qualification_pk = lookups.qualifications.get(_key(qual))
        unit_pk = lookups.units.get(_key(unit))
        if not qual or not unit:
            continue
        trainer_pks.add(trainer_pk)
        links.append(
            {
                "trainer_id": trainer_pk,
                "qualification_id": qualification_pk,
                "qualification_text": None if qualification_pk else qual,
                "unit_id": unit_pk,
                "unit_text": None if unit_pk else unit,
            }
        )

    if mode == "REPLACE" and trainer_pks:
        session.execute(delete(TrainerUnit).where(TrainerUnit.trainer_id.in_(trainer_pks)))
        session.flush()

    def identity(link: dict) -> tuple:
        """The same key the unique index uses: the id, or the normalised text."""
        return (
            link["trainer_id"],
            link["qualification_id"] or f"t:{_key(link['qualification_text'])}",
            link["unit_id"] or f"t:{_key(link['unit_text'])}",
        )

    held = {
        identity(
            {
                "trainer_id": r.trainer_id,
                "qualification_id": r.qualification_id,
                "qualification_text": r.qualification_text,
                "unit_id": r.unit_id,
                "unit_text": r.unit_text,
            }
        )
        for r in session.execute(
            select(TrainerUnit).where(TrainerUnit.trainer_id.in_(trainer_pks or {0}))
        ).scalars()
    }
    fresh = []
    for link in links:
        key = identity(link)
        if key in held:
            continue
        held.add(key)
        fresh.append(link)
    if fresh:
        session.execute(TrainerUnit.__table__.insert(), fresh)
        session.flush()

    # 2.3: derived, in bulk, for the affected trainers only. An unresolved
    # qualification contributes no link — there is no qualification to link to.
    qualification_links = rebuild_trainer_qualifications(session, sorted(trainer_pks))
    return {
        "trainers_written": 0,
        "locations_written": 0,
        "unit_links_written": len(fresh),
        "qualification_links_written": qualification_links,
        "unit_links_unresolved": sum(1 for link in fresh if link["unit_id"] is None),
        "locations_overwritten": 0,
    }


def _time(value) -> dt.time | None:
    if value is None:
        return None
    if isinstance(value, dt.time):
        return value
    try:
        return dt.time.fromisoformat(str(value))
    except ValueError:
        return None
