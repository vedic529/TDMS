"""Raise a suggestion for every unit a rolling timetable teaches but Qualification Data omits.

    python scripts/raise_rolling_timetable_units.py            # dry run
    python scripts/raise_rolling_timetable_units.py --apply    # write

College and Course Reference Data is the source: Qualification Data decides which
units belong to a qualification, and a rolling timetable orders the ones that do.
When a rolling timetable teaches a unit the source file does not list for that
qualification, the two disagree - and the reference import is right to refuse it,
because a timetable adding units to a qualification is exactly the silent drift
this project avoids.

Refusing it is not enough on its own. Reported at import time, the disagreement
scrolled past in a console and nothing carried it into the interface, so it was
invisible to whoever maintains the data. This puts it in the queue instead, as a
UNIT entry under the qualification it concerns - Qualification and Unit Sequence
is the tab that owns unit membership and the only one with a form to add it.

**The rolling timetable import now does this itself**, through the same
`raise_membership_gaps` this calls, so a gap is queued the moment a timetable is
stored. This remains for timetables imported before that was true, and as a way
to re-check the whole store without importing anything.

The entry satisfies the queue rule rather than dodging it. `rolling_timetable_weeks`
holds the qualification and unit as text with no foreign keys, so those rows are
genuinely outstanding, and `unresolved_total` counts them. Resolve it and the
membership link exists, the count falls to zero and the entry closes itself. No
sweep, no bookkeeping.

Two kinds of gap are raised the same way, because the decision is the same one -
should this unit be taught under this qualification:

* the unit exists and is simply not listed for this qualification, and
* the unit does not exist at all, so it must be created before it can be listed.

`delivery_order` is never written here. Only an approved rolling timetable
supplies a position, through the reference import (OD-07).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.services.rolling_timetable_import import (  # noqa: E402
    MEMBERSHIP_GAPS,
    raise_membership_gaps,
)

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write to the database")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)

    print(f"Rolling timetable units missing from Qualification Data - "
          f"{'APPLY' if args.apply else 'DRY RUN'}")
    print(f"  runtime role : {settings.runtime_identity}\n")

    with Session(engine) as session:
        gaps = list(session.execute(MEMBERSHIP_GAPS, {"package": None}))
        if not gaps:
            print("none - every unit a rolling timetable teaches is listed for its qualification.")
            return 0

        print(f"{'qualification':14} {'unit':14} {'weeks':>6}")
        for qualification_code, unit_code, week_rows in gaps:
            print(f"  {qualification_code:14} {str(unit_code):14} {week_rows:6}")

        # One implementation, shared with the import. A second copy here would
        # drift from it, and the two disagreeing about what counts as a gap is
        # exactly the failure this is meant to catch.
        raised = raise_membership_gaps(session)
        print(f"\n{raised} gap(s) queued.")
        print("They appear under Qualification and Unit Sequence.")

        if args.apply:
            session.commit()
            print("\ncommitted.")
        else:
            session.rollback()
            print("\nrolled back - nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
