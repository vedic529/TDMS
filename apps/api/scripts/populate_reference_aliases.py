"""Campus source addresses and superseded qualification codes.

    python scripts/populate_reference_aliases.py            # dry run
    python scripts/populate_reference_aliases.py --apply    # write

Campus addresses are read from Location Data: every distinct spelling that
derives to a campus is recorded against it, so a student file resolves whichever
form it arrives in. The supersessions are project-owner decisions and are listed
here rather than inferred — `CHC30121` and `CHC30125` differ by one digit, and
guessing the direction would move students into the wrong qualification.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

import openpyxl
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.models.college import Campus, CampusSourceAddress  # noqa: E402
from app.models.qualification import Qualification, QualificationSupersession  # noqa: E402
from app.services.reference_import import derive_campus, repair_text  # noqa: E402

from _source_data import LOCATION_FILE, require  # noqa: E402

#: Retired code -> the current code that replaced it.
#:
#: Confirmed by the project owner on 14 August 2026. Both differ from their
#: successor by a single digit, which is exactly why this is recorded rather than
#: derived: `CHC30121 -> CHC30125` and `CHC30125 -> CHC30121` are equally
#: plausible to a matcher and only one of them is true.
SUPERSESSIONS = {
    "CHC30121": "CHC30125",
    "CHC52021": "CHC52025",
}


def source_addresses() -> dict[str, set[str]]:
    """Every distinct Location Data address, grouped by the campus it derives to."""
    book = openpyxl.load_workbook(LOCATION_FILE, data_only=True)
    sheet = book[book.sheetnames[0]]
    values = list(sheet.values)
    header = [str(h).strip() if h else "" for h in values[0]]
    book.close()

    index = header.index("Location")
    grouped: dict[str, set[str]] = defaultdict(set)
    for row in values[1:]:
        if not row or index >= len(row):
            continue
        address = repair_text(row[index])
        if address:
            grouped[derive_campus(address).code].add(address)
    return grouped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    require(LOCATION_FILE.name)

    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)

    print(f"Reference aliases — {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"  runtime role: {settings.runtime_identity}\n")

    grouped = source_addresses()
    created = skipped = 0

    with Session(engine) as session:
        campuses = {c.campus_code: c for c in session.execute(select(Campus)).scalars()}
        existing = {
            row.source_address
            for row in session.execute(select(CampusSourceAddress)).scalars()
        }

        print("campus source addresses:")
        for code, addresses in sorted(grouped.items()):
            campus = campuses.get(code)
            if campus is None:
                print(f"  {code:18} SKIPPED — no such campus")
                continue
            # The campus's own stored address counts as one of its spellings, so
            # a lookup needs only this table rather than this table *and* the
            # campus row.
            for address in sorted(addresses | {campus.campus_location}):
                if address in existing:
                    skipped += 1
                    continue
                session.add(
                    CampusSourceAddress(campus_id=campus.id, source_address=address)
                )
                existing.add(address)
                created += 1
                print(f"  {campus.campus_name:18} + {address}")

        print(f"\n  created {created}, already present {skipped}")

        print("\nsuperseded qualification codes:")
        quals = {
            q.qualification_code: q
            for q in session.execute(select(Qualification)).scalars()
            if q.qualification_code
        }
        already = {
            row.superseded_code
            for row in session.execute(select(QualificationSupersession)).scalars()
        }
        for retired, current in sorted(SUPERSESSIONS.items()):
            if retired in already:
                print(f"  {retired} -> {current}  already recorded")
                continue
            if retired in quals:
                print(
                    f"  {retired} -> {current}  SKIPPED — {retired} is itself an approved "
                    "qualification, so it is not retired"
                )
                continue
            target = quals.get(current)
            if target is None:
                print(f"  {retired} -> {current}  SKIPPED — {current} is not in the reference data")
                continue
            session.add(
                QualificationSupersession(superseded_code=retired, qualification_id=target.id)
            )
            print(f"  {retired} -> {current}  recorded")

        if args.apply:
            session.commit()
            print("\ncommitted.")
        else:
            session.rollback()
            print("\nrolled back — nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
