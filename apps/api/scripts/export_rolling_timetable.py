"""Export stored rolling timetable rows as the 13-column flat file.

    python scripts/export_rolling_timetable.py --out rolling-flat.csv
    python scripts/export_rolling_timetable.py --package BSB --out bsb.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.services.rolling_timetable_import import export_flat  # noqa: E402
from app.services.rolling_timetable_store import rows_for_export  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", help="one training package, otherwise every stored row")
    parser.add_argument("--out", required=True, help="output .csv path")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)
    with Session(engine) as session:
        rows = rows_for_export(session, args.package)

    headers, body = export_flat(rows)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(body)

    print(f"wrote {len(body)} rows to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
