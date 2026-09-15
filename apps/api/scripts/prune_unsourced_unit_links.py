"""Remove qualification-unit links the source file does not list.

    python scripts/prune_unsourced_unit_links.py            # dry run
    python scripts/prune_unsourced_unit_links.py --apply    # write

College and Course Reference Data is the source. Qualification Data decides
which units belong to a qualification; a rolling timetable decides the order of
the units that belong. It does not decide what belongs.

The reference import used to ask "does this unit exist?" rather than "does
Qualification Data list this unit for this qualification?". A unit code is
globally unique, so the first question passed for any real unit, and the rolling
timetable quietly added units to a qualification its own source file does not
list - seven of them to BSB50120. The import now refuses those. This removes the
ones already written, because the import creates and reuses but never deletes.

Hard delete, not soft. `qualification_units` carries the soft-delete columns, but
those record a *decision to withdraw* something that was genuinely there. These
rows were never sourced: they are the residue of a defect, and marking them
withdrawn would assert a decision nobody made. A row removed here reappears the
moment Qualification Data lists it.

REFUSES by default to touch a link that carries a stored delivery order, on the
grounds that something ordered it deliberately and that is worth a human look
first. `--including-ordered` overrides that, and is the right flag when the order
was itself written by the defect: a position assigned to a unit that does not
belong to the qualification cannot be authoritative, because the thing being
ordered was never part of the qualification.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import openpyxl
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.models.qualification import Qualification, QualificationUnit, Unit  # noqa: E402
from app.services.reference_import import repair_text  # noqa: E402

from _source_data import QUALIFICATION_FILE, require  # noqa: E402
from set_supplied_qualification_units import SUPPLIED  # noqa: E402


def sourced_membership() -> dict[str, set[str]]:
    """Qualification code -> every unit code a source lists for it.

    Two sources, not one. Qualification Data is the usual one; a set supplied
    directly by the project owner is the other, and it is just as much a record
    of what belongs.

    Reading only the file made this script a hazard rather than a tidy-up. After
    BSB50120's 99 units were supplied - its file lists 10 - a run would have
    deleted the other 82 as unsourced, silently undoing a decision that was
    deliberately recorded. Same shape as the delivery-order bug: two sources of
    truth, and a caller that knew about one.
    """
    book = openpyxl.load_workbook(QUALIFICATION_FILE, data_only=True)
    sheet = book[book.sheetnames[0]]
    values = list(sheet.values)
    book.close()

    header = [repair_text(h) for h in values[0]]
    qi = header.index("Qualification Code")
    ui = header.index("Unit Code")

    member: dict[str, set[str]] = {
        code.upper(): {unit.upper() for unit, _title in units}
        for code, units in SUPPLIED.items()
    }
    for row in values[1:]:
        if not row:
            continue
        code = repair_text(row[qi]).upper() if qi < len(row) else ""
        unit = repair_text(row[ui]).upper() if ui < len(row) else ""
        if code and unit:
            member.setdefault(code, set()).add(unit)
    return member


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write to the database")
    parser.add_argument(
        "--including-ordered",
        action="store_true",
        help="also remove unsourced links that carry a delivery order",
    )
    args = parser.parse_args()

    require(QUALIFICATION_FILE.name)
    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)

    member = sourced_membership()
    print(f"Prune unsourced unit links - {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"  runtime role : {settings.runtime_identity}")
    print(f"  {QUALIFICATION_FILE.name:26} {len(member)} qualifications\n")

    with Session(engine) as session:
        rows = session.execute(
            select(QualificationUnit, Qualification.qualification_code, Unit.unit_code)
            .join(Qualification, Qualification.id == QualificationUnit.qualification_id)
            .join(Unit, Unit.id == QualificationUnit.unit_id)
            .order_by(Qualification.qualification_code, Unit.unit_code)
        ).all()

        removable: list[tuple] = []
        ordered: list[tuple] = []
        unlisted_qualifications: set[str] = set()

        for link, qualification_code, unit_code in rows:
            listed = member.get(qualification_code)
            if listed is None:
                # The file says nothing about this qualification at all. Silence
                # is not a withdrawal - `retire_absent_qualifications.py` is
                # where a qualification missing from the file is dealt with, and
                # deleting its units here would pre-empt that decision.
                unlisted_qualifications.add(qualification_code)
                continue
            if unit_code in listed:
                continue
            if link.delivery_order is not None and not args.including_ordered:
                ordered.append((qualification_code, unit_code, link.delivery_order))
            else:
                removable.append((link, qualification_code, unit_code))

        if unlisted_qualifications:
            print(
                f"skipped: {len(unlisted_qualifications)} qualification(s) absent from the file "
                "entirely - see retire_absent_qualifications.py\n"
            )

        if ordered:
            print(f"REFUSED - {len(ordered)} unsourced link(s) carry a delivery order:")
            for qualification_code, unit_code, position in ordered:
                print(f"  {qualification_code:12} {unit_code:12} position {position}")
            print("  Something ordered these deliberately. Left alone for a human decision.\n")

        if not removable:
            print("nothing to prune - every stored link is listed in the source file.")
            return 0

        print(f"NOT IN THE SOURCE FILE - {len(removable)}")
        for link, qualification_code, unit_code in removable:
            position = "" if link.delivery_order is None else f"  (dropping order {link.delivery_order})"
            print(f"  {qualification_code:12} {unit_code}{position}")

        for link, _code, _unit in removable:
            session.delete(link)

        print(f"\n{len(removable)} link(s) removed.")
        if args.apply:
            session.commit()
            print("\ncommitted.")
        else:
            session.rollback()
            print("\nrolled back - nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
