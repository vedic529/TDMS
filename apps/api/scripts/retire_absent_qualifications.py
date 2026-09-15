"""Retire qualifications the supplied Qualification Data no longer lists.

    python scripts/retire_absent_qualifications.py            # dry run
    python scripts/retire_absent_qualifications.py --apply    # write

The reference importer is additive by design: it creates and reuses, and never
removes, so a qualification withdrawn from the source file stays offered in TDMS
indefinitely. This is the other half of a refresh.

Retiring is `is_active = false`, not a delete. That is the approved mechanism —
"reference data ages through a status column" (DATA-03, COL-05) — and it is the
right one here for a reason beyond compliance: course offerings, allocations and
student records point at these rows, and a code withdrawn from one export is
routinely reissued in the next. A status flip is reversible; a delete is not.

Course offerings and unit memberships are deliberately left attached. They
describe what the qualification was, they are already hidden by its status, and
detaching them would destroy the only record that the offering ever existed.

REFUSES to retire a qualification that any student, allocation delivery or
trainer still depends on. A qualification missing from an export is more often an
incomplete extract than a withdrawal, and the damage from wrongly retiring a
live one is much larger than from leaving a dead one visible for another week.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import openpyxl
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.models.course import CourseOffering  # noqa: E402
from app.models.qualification import Qualification, QualificationUnit  # noqa: E402
from app.services.reference_import import repair_text  # noqa: E402

from _source_data import QUALIFICATION_FILE, require  # noqa: E402


def supplied_codes() -> set[str]:
    """Every qualification code the file lists, upper-cased."""
    book = openpyxl.load_workbook(QUALIFICATION_FILE, data_only=True)
    sheet = book[book.sheetnames[0]]
    values = list(sheet.values)
    book.close()

    header = [repair_text(h) for h in values[0]]
    index = header.index("Qualification Code")
    codes = set()
    for row in values[1:]:
        if not row or index >= len(row):
            continue
        code = repair_text(row[index]).upper()
        if code:
            codes.add(code)
    return codes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write to the database")
    args = parser.parse_args()

    require(QUALIFICATION_FILE.name)
    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)

    codes = supplied_codes()
    print(f"Retire absent qualifications — {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"  runtime role : {settings.runtime_identity}")
    print(f"  {QUALIFICATION_FILE.name:26} {len(codes)} qualification codes\n")

    with Session(engine) as session:
        # A qualification with no code is identified by title and cannot be
        # matched against this file. It is left alone rather than retired for
        # failing to appear in a column it has no value for.
        rows = session.execute(
            select(Qualification).where(Qualification.qualification_code.is_not(None))
        ).scalars()
        absent = [q for q in rows if q.qualification_code.upper() not in codes]

        if not absent:
            print("nothing to retire — every stored qualification is in the file.")
            return 0

        blocked: list[str] = []
        retire: list[tuple[Qualification, int, int]] = []

        print(f"{'code':12} {'offer':>5} {'units':>5} {'stud':>5} {'deliv':>5} {'trnq':>5}  title")
        for q in sorted(absent, key=lambda q: q.qualification_code):
            offerings = session.scalar(
                select(func.count())
                .select_from(CourseOffering)
                .where(CourseOffering.qualification_id == q.id, CourseOffering.is_deleted.is_(False))
            )
            units = session.scalar(
                select(func.count())
                .select_from(QualificationUnit)
                .where(QualificationUnit.qualification_id == q.id)
            )
            students, deliveries, trainers = (
                session.execute(text_count(sql), {"qid": q.id}).scalar()
                for sql in (STUDENT_SQL, DELIVERY_SQL, TRAINER_SQL)
            )
            depends = students + deliveries + trainers
            flag = "  BLOCKED" if depends else ""
            print(
                f"{q.qualification_code:12} {offerings:5} {units:5} {students:5} "
                f"{deliveries:5} {trainers:5}  {(q.qualification_title or '')[:38]}{flag}"
            )
            if depends:
                blocked.append(q.qualification_code)
            elif q.is_active:
                retire.append((q, offerings, units))

        if blocked:
            print(
                f"\nREFUSED: {len(blocked)} qualification(s) still have students, allocation "
                "deliveries or trainer links:\n  " + ", ".join(blocked)
            )
            print("Nothing was written. Resolve those first, or exclude them from the file check.")
            return 1

        print(
            f"\nto retire: {len(retire)} qualification(s), carrying "
            f"{sum(o for _, o, _ in retire)} course offering(s) and "
            f"{sum(u for _, _, u in retire)} unit membership(s), which stay attached."
        )
        already = len(absent) - len(retire)
        if already:
            print(f"already inactive: {already}")

        for q, _, _ in retire:
            q.is_active = False

        if args.apply:
            session.commit()
            print("\ncommitted.")
        else:
            session.rollback()
            print("\nrolled back — nothing was written.")
    return 0


from sqlalchemy import text as _text  # noqa: E402


def text_count(sql: str):
    return _text(sql)


STUDENT_SQL = (
    "select count(*) from students s join course_offerings o on o.id = s.course_offering_id "
    "where o.qualification_id = :qid and not s.is_deleted"
)
DELIVERY_SQL = "select count(*) from allocation_delivery where qualification_id = :qid"
TRAINER_SQL = "select count(*) from trainer_qualifications where qualification_id = :qid"


if __name__ == "__main__":
    raise SystemExit(main())
