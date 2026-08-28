"""Import a flat rolling timetable file.

    python scripts/import_rolling_timetable.py --package BSB --file path.csv
    python scripts/import_rolling_timetable.py --package BSB --file path.csv --apply --proceed-matching

The file is the 13-column flat format. training_package is chosen here, never
read from the file. Pass --file explicitly.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.db.enums import TRAINING_PACKAGE_VALUES  # noqa: E402
from app.services.rolling_timetable_import import (  # noqa: E402
    RollingImportError,
    apply_rows,
    review_to_dict,
    validate_bytes,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, choices=TRAINING_PACKAGE_VALUES)
    parser.add_argument("--file", required=True, help="path to a .csv or .xlsx flat file")
    parser.add_argument("--apply", action="store_true", help="write accepted rows")
    parser.add_argument(
        "--proceed-matching",
        action="store_true",
        help="when the file contains other packages, import only the selected one",
    )
    args = parser.parse_args()

    path = Path(args.file)
    if not path.is_file():
        raise SystemExit(f"File not found: {path}")

    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)
    payload = path.read_bytes()

    with Session(engine) as session:
        try:
            review, _rows = validate_bytes(
                session, training_package=args.package, file_name=path.name, payload=payload
            )
        except RollingImportError as exc:
            raise SystemExit(str(exc)) from exc

        payload_review = review_to_dict(review)
        print(f"Rolling timetable import — {'APPLY' if args.apply else 'REVIEW'}")
        print(f"  runtime role      : {settings.runtime_identity}")
        print(f"  file              : {path.name}")
        print(f"  package           : {review.training_package}")
        print(f"  status            : {review.status}")
        print(f"  rows read         : {review.rows_read}")
        print(f"  would write       : {review.rows_that_would_be_written}")
        print(f"  matching quals    : {len(review.matching_qualifications)}")
        print(f"  other quals       : {len(review.non_matching_qualifications)}")
        for item in review.non_matching_qualifications:
            print(f"    skip {item.qualification_code} ({item.row_count} rows)")
        kinds = payload_review["discrepancies_by_kind"]
        if kinds:
            print("  discrepancies:")
            for kind, items in kinds.items():
                print(f"    {kind}: {len(items)}")

        if not args.apply:
            print("\nnothing was written.")
            return 0 if not review.refused else 1

        try:
            result = apply_rows(
                session,
                training_package=args.package,
                file_name=path.name,
                payload=payload,
                proceed_with_matching=args.proceed_matching,
                user=None,
            )
            session.commit()
        except RollingImportError as exc:
            session.rollback()
            raise SystemExit(str(exc)) from exc

        print(f"\ncommitted {result.rows_written} rows.")
        if result.qualifications_skipped:
            print(f"skipped: {', '.join(result.qualifications_skipped)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
