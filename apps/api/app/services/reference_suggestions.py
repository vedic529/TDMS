"""Raise a value into the shared reference-suggestion queue.

One entry point used by every importer, so there is a single Add / Map / Reject
flow (`reference_suggestion_service.resolve_suggestion`) and a single table. This does
not create a second mechanism — it writes the same `reference_suggestion` rows
the allocation import writes, differing only in `source`.
"""

from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.allocation import ReferenceSuggestion


def _normalise(raw: str) -> str:
    return " ".join(raw.upper().split())


#: How many distinct values one attribute list keeps. A trainer seen at forty
#: campuses needs the campuses listed for a form, not an unbounded column.
_ATTRIBUTE_LIST_CAP = 50


def _is_empty(value: object) -> bool:
    return value is None or value == "" or value == [] or value == {}


def merge_attributes(held: dict | None, incoming: dict | None) -> dict:
    """Combine the pre-fill values an entry already holds with a new row's.

    A list gathers every distinct item across rows and imports - the campuses a
    trainer was seen at, the classes a unit ran in. A single value keeps the
    first one supplied: the first spelling of a unit title is as good as the
    next, and replacing it on every import would make the form flicker between
    sources for no gain.
    """
    merged = dict(held or {})
    for key, value in (incoming or {}).items():
        if _is_empty(value):
            continue
        current = merged.get(key)
        if isinstance(value, list):
            items = list(current) if isinstance(current, list) else []
            seen = {json.dumps(item, sort_keys=True) for item in items}
            for item in value:
                marker = json.dumps(item, sort_keys=True)
                if marker not in seen:
                    seen.add(marker)
                    items.append(item)
            merged[key] = items[:_ATTRIBUTE_LIST_CAP]
        elif _is_empty(current):
            merged[key] = value
    return merged


def raise_reference_suggestion(
    session: Session,
    *,
    entity_type: str,
    raw_value: str,
    context: dict,
    source: str,
    attributes: dict | None = None,
    occurrences: int = 1,
) -> bool:
    """Record an unmatched value, or increment an existing pending one.

    Returns True when a new suggestion row is created, False when an existing one
    is incremented — so a value seen on 30 rows is one suggestion with
    `occurrence_count` 30 (check R6).

    `attributes` are the raising row's other values, kept for pre-filling the
    form Add opens. They never decide which entry a value is - `context` does.
    """
    entity_type = entity_type.upper()
    normalised = _normalise(raw_value)
    context_key = json.dumps(context, sort_keys=True)
    now = dt.datetime.now(dt.timezone.utc)

    existing = session.execute(
        select(ReferenceSuggestion).where(
            ReferenceSuggestion.entity_type == entity_type,
            ReferenceSuggestion.normalised_value == normalised,
            ReferenceSuggestion.context_key == context_key,
        )
    ).scalar_one_or_none()

    if existing is not None:
        existing.occurrence_count += occurrences
        existing.last_seen_at = now
        existing.attributes = merge_attributes(existing.attributes, attributes)
        if existing.status != "PENDING":
            was_rejected = existing.status == "REJECTED"
            existing.status = "PENDING"
            existing.resolved_at = None
            existing.resolved_by_user_id = None
            existing.resolved_entity_id = None
            # An accepted exception that is raised again returns to the queue for
            # a proper decision, so the acceptance no longer stands.
            existing.accepted_by_user_id = None
            existing.accepted_at = None
            if was_rejected:
                # A rejection that turns out to be a mistake is recoverable: the
                # rows quarantined by it come back with the entry.
                from app.services.reference_suggestion_service import clear_quarantine_for

                clear_quarantine_for(session, existing)
        session.flush()
        return False

    session.add(
        ReferenceSuggestion(
            entity_type=entity_type,
            raw_value=raw_value,
            normalised_value=normalised,
            context=context,
            context_key=context_key,
            source=source,
            occurrence_count=occurrences,
            first_seen_at=now,
            last_seen_at=now,
            status="PENDING",
            attributes=merge_attributes({}, attributes),
        )
    )
    session.flush()
    return True

