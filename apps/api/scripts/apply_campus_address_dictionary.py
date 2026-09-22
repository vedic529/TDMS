"""The Campus Address Dictionary and the address corrections behind it.

    python scripts/apply_campus_address_dictionary.py            # dry run
    python scripts/apply_campus_address_dictionary.py --apply    # write

Run it **last**, after every import script: it corrects what those imports read
from the source files, and re-running `import_reference_data.py` afterwards
brings the South Melbourne campus back (run this again if that happens). Running
it twice changes nothing the second time.

Decided by the project owner on 16 September 2026:

1. A full address is identified by **college + campus**. Each approved
   combination keeps its own address (`college_campuses.address`), because one
   campus name can be a different building for each college.
2. South Melbourne is written as **Melbourne**: the South Melbourne campus is
   merged into Melbourne. NPA's Melbourne is 51 Brady St.
3. **420** Collins St is correct; 422 is a typo.
4. Hobart is **132-146** Elizabeth Street; 142-146 is a typo.
5. Brisbane is **Levels 2-3**, 18 Mt Gravatt-Capalaba Road. "Unit 2, Level 1" was
   wrong and is withdrawn. ("Mount Gravatt" in the sheet is the Brisbane campus.)
6. "AITBI" in the sheet is the college AIBT-I.

After this, the dictionary is maintained in the application:
College and Course Reference Data -> College Locations -> Address Dictionary.
Edit ``DICTIONARY`` below only to change what a fresh database is seeded with.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.models.college import Campus, CampusSourceAddress, College, CollegeCampus  # noqa: E402

#: (college short name, campus code, full address) - the owner's sheet, with the
#: corrections above applied.
DICTIONARY: list[tuple[str, str, str]] = [
    ("REACH", "HOBART", "132-146 Elizabeth Street, HOBART, Tasmania 7000"),
    ("REACH", "MELBOURNE", "Level 1 620 Bourke St, MELBOURNE, Victoria 3000"),
    ("REACH", "HAYMARKET", "Level 2, 8 Quay St, HAYMARKET, New South Wales 2000"),
    ("AVTA", "BUNDABERGCENTRAL", "10 Quay St, Bundaberg Central, Queensland 4670"),
    ("AVTA", "BLACKTOWN", "Level 2, 125 Main St, BLACKTOWN, New South Wales 2148"),
    ("AVTA", "HOBART", "132-146 Elizabeth St, Hobart, Tasmania 7000"),
    ("AVTA", "MELBOURNE", "Level 9/ 420 Collins St, MELBOURNE, Victoria 3000"),
    ("AIBT", "BLACKTOWN", "Level 2, 125 Main St, Blacktown, New South Wales 2148"),
    ("AIBT", "HAYMARKET", "841 George St, Haymarket, New South Wales 2000"),
    ("AIBT", "BRISBANE", "18 Mount Gravatt-Capalaba Rd, Levels 2-3, Upper Mount Gravatt, Queensland 4122"),
    ("AIBT", "HOBART", "132-146 Elizabeth St, Hobart, Tasmania 7000"),
    ("NPA", "HAYMARKET", "Level 2, 8 Quay St, HAYMARKET, New South Wales 2000"),
    ("NPA", "MELBOURNE", "51 Brady St, SOUTH MELBOURNE, Victoria 3205"),
    ("HJ", "HOBART", "132-146 Elizabeth Street, HOBART, TAS, 7000"),
    ("BIC", "HAYMARKET", "841 George St, Haymarket NSW 2000"),
    ("BIC", "MELBOURNE", "Victory Tower, Level 9, 420 Collins Street, Melbourne VIC 3000"),
    ("AIBT-I", "BLACKTOWN", "125 Main Street Blacktown"),
    ("AIBT-I", "BRISBANE", "18 Mt Gravatt Capalaba Rd, Upper Mt Gravatt"),
]

#: Campus merged away -> the campus it is written as.
MERGES = {"SOUTHMELBOURNE": "MELBOURNE"}

#: Typo -> correction, applied inside every stored address.
TEXT_FIXES = [
    ("422 Collins", "420 Collins"),
    ("142-146 Elizabeth", "132-146 Elizabeth"),
]

#: Spellings that named the wrong floor and are withdrawn.
WITHDRAWN = [
    "Unit 2, Level 1, 18 Mount Gravatt-Capalaba Road, Upper Mount Gravatt QLD 4122",
    "Unit 2, Level 1, 18 Mount Gravatt-Capalaba Road, Upper Mt Gravatt",
]

#: Campus code -> its corrected main address.
CAMPUS_LOCATIONS = {
    "BRISBANE": "Levels 2-3, 18 Mt Gravatt-Capalaba Road, Upper Mount Gravatt, Brisbane QLD 4122",
}


def _key(value: str) -> str:
    return " ".join(value.split()).upper()


def merge_campus(session: Session, source: Campus, target: Campus) -> None:
    """Move everything recorded against `source` onto `target`, then remove it."""
    s, t = source.id, target.id
    for link in session.execute(select(CollegeCampus).where(CollegeCampus.campus_id == s)).scalars().all():
        if session.get(CollegeCampus, (link.college_id, t)) is None:
            session.add(
                CollegeCampus(
                    college_id=link.college_id, campus_id=t, is_active=link.is_active, address=link.address
                )
            )
    session.flush()

    clash = session.execute(
        text(
            "SELECT count(*) FROM course_offerings a JOIN course_offerings b "
            "ON a.college_id = b.college_id AND a.qualification_id = b.qualification_id "
            "WHERE a.campus_id = :s AND b.campus_id = :t"
        ),
        {"s": s, "t": t},
    ).scalar_one()
    clash += session.execute(
        text(
            "SELECT count(*) FROM facilities a JOIN facilities b "
            "ON a.source_location = b.source_location AND a.facility_reference = b.facility_reference "
            "WHERE a.campus_id = :s AND b.campus_id = :t"
        ),
        {"s": s, "t": t},
    ).scalar_one()
    if clash:
        raise SystemExit(
            f"{source.campus_name} cannot merge into {target.campus_name}: {clash} record(s) exist at both."
        )

    for table, column in (
        ("course_offerings", "campus_id"),
        ("facilities", "campus_id"),
        ("trainer_availability", "campus_id"),
        ("allocation_delivery", "campus_id"),
        ("campus_source_addresses", "campus_id"),
        ("import_staged_rows", "resolved_campus_id"),
    ):
        moved = session.execute(
            text(f"UPDATE {table} SET {column} = :t WHERE {column} = :s"), {"s": s, "t": t}
        ).rowcount
        print(f"    {table:24} {moved} moved")
    session.execute(
        text(
            "UPDATE reference_suggestion SET resolved_entity_id = :t "
            "WHERE entity_type = 'CAMPUS' AND resolved_entity_id = :s"
        ),
        {"s": s, "t": t},
    )
    session.execute(text("DELETE FROM college_campuses WHERE campus_id = :s"), {"s": s})
    # The campus's own name and address stay matchable as spellings of the target.
    for spelling in (source.campus_name, source.campus_location):
        if not session.execute(
            select(CampusSourceAddress).where(
                func.upper(CampusSourceAddress.source_address) == spelling.upper()
            )
        ).scalars().first():
            session.add(CampusSourceAddress(campus_id=t, source_address=spelling))
    session.flush()
    session.delete(source)
    session.flush()


def fix_spellings(session: Session) -> None:
    for wrong, right in TEXT_FIXES:
        for row in session.execute(
            select(CampusSourceAddress).where(CampusSourceAddress.source_address.contains(wrong))
        ).scalars().all():
            corrected = row.source_address.replace(wrong, right)
            duplicate = session.execute(
                select(CampusSourceAddress).where(CampusSourceAddress.source_address == corrected)
            ).scalars().first()
            if duplicate is not None:
                print(f"  - {row.source_address}  (already recorded as {corrected})")
                session.delete(row)
            else:
                print(f"  ~ {row.source_address}  ->  {corrected}")
                row.source_address = corrected
        session.flush()
        for table, column in (("facilities", "source_location"), ("campuses", "campus_location")):
            changed = session.execute(
                text(f"UPDATE {table} SET {column} = replace({column}, :w, :r) WHERE {column} LIKE :like"),
                {"w": wrong, "r": right, "like": f"%{wrong}%"},
            ).rowcount
            if changed:
                print(f"  ~ {table}.{column}: {changed} row(s) '{wrong}' -> '{right}'")

    for spelling in WITHDRAWN:
        gone = session.execute(
            text("DELETE FROM campus_source_addresses WHERE source_address = :a"), {"a": spelling}
        ).rowcount
        if gone:
            print(f"  - {spelling}  (withdrawn)")

    for code, location in CAMPUS_LOCATIONS.items():
        campus = session.execute(select(Campus).filter_by(campus_code=code)).scalar_one_or_none()
        if campus is not None and campus.campus_location != location:
            print(f"  ~ {campus.campus_name} main address: {campus.campus_location}  ->  {location}")
            campus.campus_location = location
    session.flush()


def seed_dictionary(session: Session) -> int:
    colleges = {c.college_short_name: c for c in session.execute(select(College)).scalars()}
    campuses = {c.campus_code: c for c in session.execute(select(Campus)).scalars()}
    spellings = {
        _key(row.source_address): row.campus_id
        for row in session.execute(select(CampusSourceAddress)).scalars()
    }
    problems = 0
    for college_name, code, address in DICTIONARY:
        college, campus = colleges.get(college_name), campuses.get(code)
        label = f"{college_name} / {code}"
        if college is None or campus is None:
            print(f"  ! {label:26} SKIPPED - {'college' if college is None else 'campus'} not found")
            problems += 1
            continue
        owner = spellings.get(_key(address))
        if owner is not None and owner != campus.id:
            print(f"  ! {label:26} SKIPPED - the address is recorded for another campus")
            problems += 1
            continue
        link = session.get(CollegeCampus, (college.id, campus.id))
        if link is None:
            link = CollegeCampus(college_id=college.id, campus_id=campus.id, is_active=True)
            session.add(link)
        if link.address == address:
            print(f"    {label:26} unchanged")
        else:
            print(f"  + {label:26} {address}")
            link.address = address
        if owner is None:
            session.add(CampusSourceAddress(campus_id=campus.id, source_address=address))
            spellings[_key(address)] = campus.id
    session.flush()
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)
    print(f"Campus Address Dictionary - {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"  runtime role: {settings.runtime_identity}\n")

    with Session(engine) as session:
        print("Campus merges:")
        for source_code, target_code in MERGES.items():
            source = session.execute(select(Campus).filter_by(campus_code=source_code)).scalar_one_or_none()
            target = session.execute(select(Campus).filter_by(campus_code=target_code)).scalar_one_or_none()
            if source is None:
                print(f"  {source_code} -> {target_code}: already merged")
            elif target is None:
                print(f"  {source_code} -> {target_code}: SKIPPED - {target_code} not found")
            else:
                print(f"  {source.campus_name} -> {target.campus_name}")
                merge_campus(session, source, target)

        print("\nAddress corrections:")
        fix_spellings(session)

        print("\nDictionary:")
        problems = seed_dictionary(session)

        if args.apply:
            session.commit()
            print("\nApplied.")
        else:
            session.rollback()
            print("\nDry run - nothing written. Re-run with --apply.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
