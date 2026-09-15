"""Full College and Course Reference Data import.

    python scripts/import_reference_data.py            # dry run, writes nothing
    python scripts/import_reference_data.py --apply    # write

Runs as the least-privilege `tdms_app` role — the same role FastAPI uses — so a
privilege the application lacks fails here rather than in production. The whole
import is one transaction: it lands complete or not at all.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import openpyxl
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.services.reference_import import ReferenceImporter, format_report  # noqa: E402
from app.services.rolling_timetable import load_workbook_sheet  # noqa: E402

from _source_data import (  # noqa: E402
    LOCATION_FILE,
    QUALIFICATION_FILE,
    ROLLING_FILE,
    require,
)

#: Sheet names look like `BSB50420_52_Weeks`: the qualification code, then the
#: course length.
_SHEET_NAME = re.compile(r"^(?P<code>[A-Z]{3}\d{5})_\d+_Weeks$", re.IGNORECASE)


def rolling_sheets(session: Session) -> dict[str, str]:
    """Qualification code -> sheet, for every rolling timetable that is loaded.

    Read from the workbook rather than listed here. This was
    `{"BSB50420": "BSB50420_52_Weeks"}` - one entry, hard-coded - while the file
    held thirteen. So twelve qualifications that *do* have an approved rolling
    timetable were reported as having no approved delivery sequence, and the
    interface said so on their behalf.

    The order still comes only from an approved rolling timetable and is never
    invented: a qualification with no sheet keeps its membership and no
    sequence, exactly as before. Reading the list from the file means adding a
    sheet is enough - there is no second place to remember to update, which is
    what went wrong here.

    A sheet is used only once its rolling timetable has been **imported**, which
    is the difference between a timetable this system runs on and a spreadsheet
    that happens to sit in the same workbook. FNS40222, FNS50222 and FNS60222
    are in the file but their training package has not been imported, and taking
    their sequence anyway gave three qualifications a teaching order from a
    timetable TDMS does not hold - a sequence with nothing behind it.

    Stated as a rule rather than an exclusion list: the sheet is used when
    `rolling_timetable_weeks` holds that qualification. FNS starts being used the
    day its rolling timetable is imported, and no one has to remember to come
    back and edit this.
    """
    loaded = {
        str(row[0]).strip().upper()
        for row in session.execute(
            text("select distinct qualification_code from rolling_timetable_weeks")
        )
        if row[0]
    }

    book = openpyxl.load_workbook(ROLLING_FILE, read_only=True, data_only=True)
    found: dict[str, str] = {}
    skipped: list[str] = []
    for name in book.sheetnames:
        match = _SHEET_NAME.match(name.strip())
        if not match:
            continue
        code = match.group("code").upper()
        if code in loaded:
            found[code] = name
        else:
            skipped.append(code)
    book.close()

    if skipped:
        print(
            f"  rolling timetables in the file but not imported: {', '.join(sorted(skipped))}"
            " - no delivery order is taken from them"
        )
    return found


def read(path: Path) -> list[dict]:
    book = openpyxl.load_workbook(path, data_only=True)
    sheet = book[book.sheetnames[0]]
    values = list(sheet.values)
    header = [str(h).strip() if h else "" for h in values[0]]
    book.close()
    return [
        dict(zip(header, row))
        for row in values[1:]
        if any(cell is not None and str(cell).strip() for cell in row)
    ]


def base_cycles(sheets: dict[str, str]) -> dict[str, list[str]]:
    """Approved delivery order per qualification, read from the rolling timetable.

    The order is the earliest complete stream's unit progression — the base
    rolling cycle. It is evidence, not an assumption, and intakes join it at
    different points, which `delivery_order` does not attempt to express.
    """
    cycles: dict[str, list[str]] = {}
    for code, sheet_name in sheets.items():
        sheet = load_workbook_sheet(str(ROLLING_FILE), sheet_name)
        seen: list[str] = []
        for delivery in sheet.intakes[0].unit_deliveries:
            if delivery.unit_code not in seen:
                seen.append(delivery.unit_code)
        cycles[code] = seen
    return cycles


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write to the database")
    args = parser.parse_args()

    require(LOCATION_FILE.name, QUALIFICATION_FILE.name, ROLLING_FILE.name)

    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)

    location_rows = read(LOCATION_FILE)
    qualification_rows = read(QUALIFICATION_FILE)

    print(f"College and Course Reference Data import — {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"  runtime role      : {settings.runtime_identity}")
    print(f"  {LOCATION_FILE.name:32} {len(location_rows)} rows")
    print(f"  {QUALIFICATION_FILE.name:32} {len(qualification_rows)} rows")

    with Session(engine) as probe:
        cycles = base_cycles(rolling_sheets(probe))
    for code, order in cycles.items():
        print(f"  approved sequence source        : {code} ({len(order)} units, from rolling timetable)")

    with Session(engine) as session:
        importer = ReferenceImporter(session, sequence_sources=cycles)
        report = importer.run(location_rows, qualification_rows)
        print(format_report(report))

        if args.apply:
            session.commit()
            print("\ncommitted.")
        else:
            session.rollback()
            print("\nrolled back — nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
