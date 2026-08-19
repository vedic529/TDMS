"""Real trainer import from `Trainer Data - BSB.xlsx`.

    python scripts/import_trainers.py            # dry run
    python scripts/import_trainers.py --apply    # write

Runs as the least-privilege `tdms_app` role. One transaction: complete or none.

Nothing is invented. Working time, delivery type, the five weekday availability
values, campus, qualification competency and unit competency all come from the
workbook; anything the workbook does not state is left empty and reported.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.models.college import Campus  # noqa: E402
from app.models.qualification import Qualification, Unit  # noqa: E402
from app.models.trainer import (  # noqa: E402
    Trainer,
    TrainerAvailability,
    TrainerQualification,
    TrainerUnit,
)

from _source_data import TRAINER_FILE, require  # noqa: E402

WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")

#: Trainer Location values that are not a physical campus.
#:
#: "Offshore" is a delivery arrangement, not a site in `campuses`, and there is
#: no approved campus for it. Availability rows for it are reported rather than
#: forced onto an unrelated campus to satisfy a foreign key.
NON_CAMPUS_LOCATIONS = {"OFFSHORE"}


def rows(sheet_name: str) -> list[dict]:
    book = openpyxl.load_workbook(TRAINER_FILE, data_only=True)
    sheet = book[sheet_name]
    values = list(sheet.values)
    header = [str(h).strip() if h else "" for h in values[0]]
    book.close()
    return [
        dict(zip(header, r))
        for r in values[1:]
        if any(c is not None and str(c).strip() for c in r)
    ]


#: Zero-width and non-breaking characters the workbook carries invisibly.
#:
#: `\s` does not match U+200B, so "​​FNSACC601" compared unequal to
#: "FNSACC601" and the unit looked missing. Invisible in the spreadsheet,
#: invisible in the error message, and entirely responsible for the mismatch.
_INVISIBLE = re.compile(r"[​‌‍﻿\xa0]")


def cell(row: dict, key: str) -> str:
    value = row.get(key)
    if value is None:
        return ""
    return re.sub(r"\s+", " ", _INVISIBLE.sub(" ", str(value))).strip()


def parse_working_time(text: str) -> tuple[dt.time, dt.time] | None:
    """Read "9:00 AM to 5:00 PM AEST/AEDT" into two times.

    Returns None rather than a default when the text cannot be read: a made-up
    9-to-5 would look identical to a real one and would be used for availability
    checks.
    """
    found = re.findall(r"(\d{1,2})(?::(\d{2}))?\s*([AaPp][Mm])", text)
    if len(found) < 2:
        return None

    def to_time(part) -> dt.time:
        hour, minute, meridiem = int(part[0]), int(part[1] or 0), part[2].upper()
        if meridiem == "PM" and hour != 12:
            hour += 12
        if meridiem == "AM" and hour == 12:
            hour = 0
        return dt.time(hour, minute)

    return to_time(found[0]), to_time(found[1])


def weekday_mode(value: str) -> str:
    cleaned = value.strip().upper()
    if cleaned in ("", "NA", "N/A", "-"):
        return "NOT_AVAILABLE"
    return cleaned if cleaned in ("PHYSICAL", "VIRTUAL") else "NOT_AVAILABLE"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    require(TRAINER_FILE.name)

    locations = rows("Trainer Location")
    competencies = rows("Trainer Units")

    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)

    created = defaultdict(int)
    reused = defaultdict(int)
    issues: list[str] = []

    print(f"Trainer import — {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"  runtime role        : {settings.runtime_identity}")
    print(f"  Trainer Location    : {len(locations)} rows")
    print(f"  Trainer Units       : {len(competencies)} rows")

    with Session(engine) as session:
        campuses = {
            c.campus_name.strip().upper(): c
            for c in session.execute(select(Campus)).scalars()
        }
        quals = {
            q.qualification_code.strip().upper(): q
            for q in session.execute(select(Qualification)).scalars()
            if q.qualification_code
        }
        units = {
            u.unit_code.strip().upper(): u for u in session.execute(select(Unit)).scalars()
        }

        def get_or_create(model, defaults: dict, **lookup):
            existing = session.execute(select(model).filter_by(**lookup)).scalar_one_or_none()
            if existing is not None:
                reused[model.__name__] += 1
                return existing
            row = model(**lookup, **defaults)
            session.add(row)
            session.flush()
            created[model.__name__] += 1
            return row

        trainers: dict[str, Trainer] = {}
        for index, row in enumerate(locations, start=2):
            code = cell(row, "Trainer id")
            if not code:
                issues.append(f"Trainer Location row {index}: no Trainer id.")
                continue

            trainer = trainers.get(code)
            if trainer is None:
                trainer = get_or_create(
                    Trainer,
                    {"trainer_name": cell(row, "Trainer name"), "is_active": True},
                    trainer_id=code,
                )
                trainers[code] = trainer

            location = cell(row, "Location")
            if location.upper() in NON_CAMPUS_LOCATIONS:
                issues.append(
                    f"Trainer Location row {index}: {code} at {location!r} — not a physical "
                    "campus in the approved reference data, so no availability row was written."
                )
                continue

            campus = campuses.get(location.upper())
            if campus is None:
                issues.append(
                    f"Trainer Location row {index}: {code} at {location!r} — no campus of "
                    "that name exists in the approved reference data."
                )
                continue

            window = parse_working_time(cell(row, "Working Time"))
            if window is None:
                issues.append(
                    f"Trainer Location row {index}: working time "
                    f"{cell(row, 'Working Time')!r} could not be read; row skipped rather "
                    "than given invented hours."
                )
                continue

            class_type = cell(row, "Delivery Type").upper() or "THEORY"
            get_or_create(
                TrainerAvailability,
                {
                    "location": location,
                    "location_type": cell(row, "Location Type") or None,
                    "working_time_end": window[1],
                    **{day.lower(): weekday_mode(cell(row, day)) for day in WEEKDAYS},
                },
                trainer_id=trainer.id,
                campus_id=campus.id,
                class_type=class_type,
                working_time_start=window[0],
            )

        for index, row in enumerate(competencies, start=2):
            code = cell(row, "Trainer ID")
            trainer = trainers.get(code)
            if trainer is None:
                issues.append(
                    f"Trainer Units row {index}: {code} has no Trainer Location record."
                )
                continue

            qualification = quals.get(cell(row, "Qualifications They Can Teach").upper())
            if qualification is None:
                issues.append(
                    f"Trainer Units row {index}: qualification "
                    f"{cell(row, 'Qualifications They Can Teach')!r} is not in the reference data."
                )
            else:
                get_or_create(
                    TrainerQualification, {},
                    trainer_id=trainer.id, qualification_id=qualification.id,
                )

            unit = units.get(cell(row, "Units They Can Teach").upper())
            if unit is None:
                issues.append(
                    f"Trainer Units row {index}: unit "
                    f"{cell(row, 'Units They Can Teach')!r} is not in the reference data."
                )
                continue
            get_or_create(TrainerUnit, {}, trainer_id=trainer.id, unit_id=unit.id)

        print("\n  created:", dict(created) or "none")
        print("  reused :", dict(reused) or "none")
        if issues:
            print(f"\n  reported, not invented ({len(issues)}):")
            for issue in sorted(set(issues))[:10]:
                print(f"    - {issue}")
            if len(set(issues)) > 10:
                print(f"    - ... and {len(set(issues)) - 10} more")

        if args.apply:
            session.commit()
            print("\ncommitted.")
        else:
            session.rollback()
            print("\nrolled back — nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
