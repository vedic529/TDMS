"""Re-check open suggestions and exceptions against the current reference data.

    python scripts/recalibrate_suggestions.py            # dry run
    python scripts/recalibrate_suggestions.py --apply    # write

A queue entry records that a value could not be resolved *at the time it was
imported*. Reference data moves on: a college is added, a campus records another
spelling, a qualification arrives in the next export. Nothing re-examines the
queue when that happens, so an entry can sit there long after the thing it was
waiting for exists - and an accepted exception is worse than a pending one,
because it is a standing instruction to ignore a value TDMS can now resolve.

This is the sweep that closes that gap. It resolves through
`resolve_suggestion`, so the relink, the audit record and the changed-row count
are identical to an administrator clicking Map in the queue.

MATCHES ON EVIDENCE ONLY. A value is mapped when it equals a stored name, code
or recorded spelling under the same normaliser the queue itself uses. Nothing is
matched on a prefix, a substring or a similarity score: `Sydney (Haymarket)` is
almost certainly the Haymarket campus, but "almost certainly" is the judgement
the queue exists to put in front of a person. Those are reported as needing a
decision, never guessed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.models.college import Campus, CampusSourceAddress, College  # noqa: E402
from app.models.facility import Facility  # noqa: E402
from app.models.qualification import Qualification, Unit  # noqa: E402
from app.models.allocation import ReferenceSuggestion  # noqa: E402
from app.models.trainer import Trainer  # noqa: E402
from app.models.user import User  # noqa: E402
from app.services.reference_suggestion_service import (  # noqa: E402
    prune_empty,
    resolve_suggestion,
    unresolved_total,
)

#: Statuses still awaiting a real decision. `MAPPED`, `ADDED` and `REJECTED` are
#: decided and are never revisited - reopening a decision a person made is not
#: this script's business.
OPEN_STATUSES = ("PENDING", "EXCEPTION")


def normalised(column):
    """The queue's own normaliser, in SQL.

    Must stay identical to `reference_suggestion_service._normalised`: this
    compares against `normalised_value`, which was written with it.
    """
    return func.upper(func.btrim(func.regexp_replace(column, r"\s+", " ", "g")))


def candidates(session: Session, entity: str, value: str) -> list[tuple[int, str]]:
    """Every stored record whose identifying text equals `value`.

    More than one hit means the value is genuinely ambiguous, and it is reported
    rather than resolved to whichever record the database returned first.
    """

    def hits(model, *columns) -> dict[int, str]:
        found: dict[int, str] = {}
        for column in columns:
            for row in session.execute(
                select(model).where(normalised(column) == value)
            ).scalars():
                found[row.id] = str(getattr(row, columns[0].key) or row.id)
        return found

    if entity == "COLLEGE":
        return sorted(hits(College, College.college_short_name, College.college_full_name).items())

    if entity == "CAMPUS":
        found = hits(
            Campus, Campus.campus_name, Campus.campus_code, Campus.campus_location
        )
        # A recorded spelling counts as evidence. It is how this project already
        # says "this wording means that site", and the facility import has
        # trusted it since it was written.
        for alias in session.execute(
            select(CampusSourceAddress).where(
                normalised(CampusSourceAddress.source_address) == value
            )
        ).scalars():
            campus = session.get(Campus, alias.campus_id)
            if campus is not None:
                found.setdefault(campus.id, campus.campus_name)
        return sorted(found.items())

    if entity == "QUALIFICATION":
        return sorted(
            hits(
                Qualification,
                Qualification.qualification_code,
                Qualification.qualification_title,
            ).items()
        )
    if entity == "UNIT":
        return sorted(hits(Unit, Unit.unit_code, Unit.unit_title).items())
    if entity == "FACILITY":
        return sorted(hits(Facility, Facility.facility_reference).items())
    if entity == "TRAINER":
        return sorted(hits(Trainer, Trainer.trainer_name).items())
    return []


def is_membership_decision(row) -> bool:
    """Does resolving this entry decide membership rather than identity?

    A UNIT entry carrying a qualification asks "should this qualification teach
    this unit". No lookup answers that, so it is never resolved automatically
    however cleanly the code matches.
    """
    return row.entity_type == "UNIT" and bool((row.context or {}).get("qualification"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write to the database")
    parser.add_argument(
        "--as-user",
        type=int,
        help="user id to attribute the resolutions to (default: the first SUPER_ADMIN)",
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url, future=True)

    print(f"Recalibrate suggestions - {'APPLY' if args.apply else 'DRY RUN'}")
    print(f"  runtime role : {settings.runtime_identity}")

    with Session(engine) as session:
        if args.as_user:
            user = session.get(User, args.as_user)
        else:
            user = (
                session.execute(
                    select(User)
                    .where(User.access_level == "SUPER_ADMIN")
                    .order_by(User.id)
                )
                .scalars()
                .first()
            )
        if user is None:
            print("\nNo user to attribute the resolutions to. Pass --as-user.")
            return 1
        print(f"  resolving as : {user.display_name} (#{user.id})\n")

        rows = list(
            session.execute(
                select(ReferenceSuggestion)
                .where(ReferenceSuggestion.status.in_(OPEN_STATUSES))
                .order_by(ReferenceSuggestion.entity_type, ReferenceSuggestion.raw_value)
            ).scalars()
        )
        if not rows:
            print("the queue has no open entries.")
            return 0

        needs_person: list[ReferenceSuggestion] = []
        resolvable: list[tuple[ReferenceSuggestion, int, str]] = []
        ambiguous: list[tuple[ReferenceSuggestion, list]] = []
        unmatched: list[ReferenceSuggestion] = []

        for row in rows:
            if is_membership_decision(row):
                # A UNIT entry scoped to a qualification asks whether that
                # qualification should teach the unit. Finding a unit with the
                # same code answers a different question - the unit exists, and
                # existing says nothing about where it belongs. Auto-mapping on
                # that would let a rolling timetable add units to a
                # qualification by itself, which is the drift the
                # source-of-truth rule forbids.
                needs_person.append(row)
                continue
            found = candidates(session, row.entity_type, row.normalised_value)
            if len(found) == 1:
                resolvable.append((row, found[0][0], found[0][1]))
            elif found:
                ambiguous.append((row, found))
            else:
                unmatched.append(row)

        print(f"open entries: {len(rows)}\n")

        if needs_person:
            print(f"A PERSON MUST DECIDE - {len(needs_person)} (membership, not identity)")
            for row in needs_person:
                behind = unresolved_total(
                    session, row.entity_type, row.normalised_value, row.context
                )
                scope = (row.context or {}).get("qualification", "")
                print(
                    f"  {row.entity_type:6} {row.raw_value:12} under {scope:10} "
                    f"{behind} rolling-timetable row(s) behind it"
                )
            print("  Never auto-mapped: whether a qualification teaches a unit is a decision.")
            print()

        if resolvable:
            print(f"NOW RESOLVABLE - {len(resolvable)}")
            for row, entity_id, label in resolvable:
                print(
                    f"  {row.status:9} {row.entity_type:13} {row.raw_value!r} "
                    f"x{row.occurrence_count}  ->  {label} (#{entity_id})"
                )
            print()

        if ambiguous:
            print(f"AMBIGUOUS - {len(ambiguous)} (more than one record has this exact text)")
            for row, found in ambiguous:
                names = ", ".join(f"{label} (#{i})" for i, label in found)
                print(f"  {row.entity_type:13} {row.raw_value!r} -> {names}")
            print()

        if unmatched:
            print(f"STILL NEEDS A DECISION - {len(unmatched)} (no stored record has this text)")
            for row in unmatched:
                behind = unresolved_total(
                    session, row.entity_type, row.normalised_value, row.context
                )
                print(
                    f"  {row.status:9} {row.entity_type:13} {row.raw_value!r} "
                    f"{behind} row(s) behind it, seen {row.occurrence_count} time(s) "
                    f"on import, from {row.source}"
                )
            print()

        # An entry with nothing behind it offers a decision that changes
        # nothing. Pruning runs before the mapping below, so the mapping is
        # never applied to an entry that should not exist.
        emptied = prune_empty(session)
        if emptied:
            print(f"NOTHING BEHIND THEM - {len(emptied)}, removed")
            for entry in emptied:
                print(
                    f"  {entry['status']:9} {entry['entity_type']:13} {entry['raw_value']!r} "
                    f"(seen {entry['occurrence_count']} time(s) on import, "
                    f"from {entry['source']})"
                )
            print()
            resolvable = [r for r in resolvable if r[0].id not in {e["id"] for e in emptied}]

        if not resolvable:
            print("nothing further to recalibrate.")
            if args.apply and emptied:
                session.commit()
                print("\ncommitted.")
            elif emptied:
                session.rollback()
                print("\nrolled back - nothing was written.")
            return 0

        total = 0
        for row, entity_id, label in resolvable:
            _, updated = resolve_suggestion(
                session,
                user,
                suggestion_id=row.id,
                action="MAP",
                resolved_entity_id=entity_id,
            )
            total += updated
            print(f"  mapped {row.raw_value!r} -> {label}: {updated} stored record(s) relinked")

        print(f"\n{len(resolvable)} entry(ies) mapped, {total} stored record(s) relinked.")
        if total == 0:
            print(
                "No stored rows changed. That is expected where the rows an entry came\n"
                "from were dropped at import rather than kept with their text - those\n"
                "come back only on a re-import, now that the value resolves."
            )

        if args.apply:
            session.commit()
            print("\ncommitted.")
        else:
            session.rollback()
            print("\nrolled back - nothing was written.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
