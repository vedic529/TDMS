"""Merge trainer suggestions that one name was split into, and remove empty entries.

    python scripts/merge_split_suggestions.py            # dry run, writes nothing
    python scripts/merge_split_suggestions.py --apply    # write

Until 15 September 2026 a trainer suggestion was keyed by the name *and* the
college on the row, so one misspelt name became an entry per college - while Map
repaired every class carrying the name, whichever college. Mapping one entry
emptied the rest, and they stayed in the queue reading "0 affected records".

This does what the new key would have done from the start:

1. Every open TRAINER entry for the same name becomes one entry with no context.
   The occurrence counts are added up and the pre-fill values combined. An entry
   already keyed without a college is the one kept; otherwise the earliest.
2. Every open entry, of any kind, with nothing stored behind it is removed.

A resolved entry is never touched: it is the record of a decision.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db.session import get_session_factory  # noqa: E402
from app.models.allocation import ReferenceSuggestion  # noqa: E402
from app.services.reference_suggestion_service import prune_empty  # noqa: E402
from app.services.reference_suggestions import merge_attributes  # noqa: E402

OPEN = ("PENDING", "EXCEPTION")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the changes")
    args = parser.parse_args()

    session = get_session_factory()()
    try:
        groups: dict[str, list[ReferenceSuggestion]] = defaultdict(list)
        for entry in session.execute(
            select(ReferenceSuggestion)
            .where(ReferenceSuggestion.entity_type == "TRAINER", ReferenceSuggestion.status.in_(OPEN))
            .order_by(ReferenceSuggestion.id)
        ).scalars():
            groups[entry.normalised_value].append(entry)

        merged = 0
        for value, entries in groups.items():
            unscoped = session.execute(
                select(ReferenceSuggestion).where(
                    ReferenceSuggestion.entity_type == "TRAINER",
                    ReferenceSuggestion.normalised_value == value,
                    ReferenceSuggestion.context_key == "{}",
                )
            ).scalar_one_or_none()
            if len(entries) == 1 and entries[0].context_key == "{}":
                continue

            keep = unscoped if unscoped is not None else entries[0]
            others = [entry for entry in entries if entry.id != keep.id]
            print(
                f"  {entries[0].raw_value!r}: keeping #{keep.id}, merging "
                f"{', '.join(f'#{e.id} {e.context}' for e in others) or 'nothing'}"
            )
            total = keep.occurrence_count
            attributes = dict(keep.attributes or {})
            for entry in others:
                total += entry.occurrence_count
                attributes = merge_attributes(attributes, entry.attributes)
                session.delete(entry)
            # The duplicates go first: the kept entry takes their key next.
            session.flush()
            if keep.status not in OPEN:
                # A resolved no-context entry absorbing open ones is reopened -
                # the same thing raising the value again would have done.
                keep.status = "PENDING"
                keep.resolved_at = None
                keep.resolved_by_user_id = None
                keep.resolved_entity_id = None
            keep.context = {}
            keep.context_key = "{}"
            keep.occurrence_count = total
            keep.attributes = attributes
            session.flush()
            merged += len(others)

        removed = prune_empty(session)
        for entry in removed:
            print(f"  removed empty #{entry['id']} {entry['entity_type']} {entry['raw_value']!r} ({entry['status']})")
        print(f"\n{merged} trainer entr{'y' if merged == 1 else 'ies'} merged, {len(removed)} empty entr{'y' if len(removed) == 1 else 'ies'} removed.")

        if args.apply:
            session.commit()
            print("Written.")
        else:
            session.rollback()
            print("Dry run - nothing written. Re-run with --apply to write.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
