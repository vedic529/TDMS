"""Approved full legal names and student email domains for the six colleges.

    python scripts/set_college_email_domains.py            # dry run
    python scripts/set_college_email_domains.py --apply    # write

Supplied by the project owner on 13 August 2026. They are recorded here rather
than inferred: a college's marketing domain is not necessarily the domain its
student mailboxes live on, and `Qualification Data.xlsx` carries
`aibtglobal.edu.au` as a course page URL, which is a different fact.

`colleges.email_domain` already existed, so no migration is needed. The values
go in the database because SRS §6.1.3 builds the proposed student College Email
from them, and a domain hard-coded in a React component or a Python dict is one
that will disagree with the database the first time a college is renamed.

Stored without the leading '@': the column holds the domain, and the address
format belongs to the email-building rule, not to reference data.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.models.college import College  # noqa: E402

#: Full legal names, supplied by the project owner on 13 August 2026.
#:
#: Until now `college_full_name` held the short name, because no supplied file
#: contained the legal names and inventing one was not an option.
APPROVED_FULL_NAMES = {
    "AIBT": "Australia Institute of Business and Technology",
    "AVTA": "Australian Vocational Training Academy",
    "BIC": "Brooklyn International College Australia",
    "HJ": "HJ Australian Institute",
    "NPA": "National Polytechnic of Australia",
    "REACH": "Reach Community College",
}

#: College short name -> approved student email domain.
#:
#: Two of these confirm something already suspected: `BIC` uses
#: `brooklyn.edu.au` and `HJ` uses `hjaustralianinstitute.edu.au`, matching the
#: `Brooklyn` and `HJAI` RTO names in Qualification Data. The reference import
#: flagged those as unmapped names; they are the same organisations.
#:
#: These are **student** email domains. They are not TDMS staff login domains,
#: which are governed by the Entra tenant rules and must stay separate.
APPROVED_DOMAINS = {
    "AIBT": "aibtglobal.edu.au",
    "AVTA": "avta.edu.au",
    "BIC": "brooklyn.edu.au",
    "HJ": "hjaustralianinstitute.edu.au",
    "NPA": "npa.edu.au",
    "REACH": "reachcollege.edu.au",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)

    print(f"College email domains — {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"  runtime role: {settings.runtime_identity}\n")

    missing: list[str] = []
    with Session(engine) as session:
        colleges = {
            c.college_short_name: c for c in session.execute(select(College)).scalars()
        }

        for short_name, domain in sorted(APPROVED_DOMAINS.items()):
            college = colleges.get(short_name)
            if college is None:
                missing.append(short_name)
                print(f"  {short_name:6} SKIPPED — no such college in the reference data")
                continue
            full_name = APPROVED_FULL_NAMES.get(short_name)
            if full_name and college.college_full_name != full_name:
                print(f"  {short_name:6} name   {college.college_full_name!r} -> {full_name!r}")
                college.college_full_name = full_name

            before = college.email_domain or "(empty)"
            if college.email_domain == domain:
                print(f"  {short_name:6} domain unchanged  {domain}")
                continue
            college.email_domain = domain
            print(f"  {short_name:6} domain {before} -> {domain}")

        unlisted = sorted(set(colleges) - set(APPROVED_DOMAINS))
        for short_name in unlisted:
            print(f"  {short_name:6} NO DOMAIN SUPPLIED — left empty, not guessed")

        if args.apply:
            session.commit()
            print("\ncommitted.")
        else:
            session.rollback()
            print("\nrolled back — nothing was written.")

    if missing:
        print(f"\nnot found in the database: {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
