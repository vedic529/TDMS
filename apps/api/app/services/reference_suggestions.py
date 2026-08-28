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


def raise_reference_suggestion(
    session: Session,
    *,
    entity_type: str,
    raw_value: str,
    context: dict,
    source: str,
) -> bool:
    """Record an unmatched value, or increment an existing pending one.

    Returns True when a new suggestion row is created, False when an existing one
    is incremented — so a value seen on 30 rows is one suggestion with
    `occurrence_count` 30 (check R6).
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
        existing.occurrence_count += 1
        existing.last_seen_at = now
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
            occurrence_count=1,
            first_seen_at=now,
            last_seen_at=now,
            status="PENDING",
        )
    )
    session.flush()
    return True


def record_reference_exception(
    session: Session,
    *,
    entity_type: str,
    raw_value: str,
    context: dict,
    source: str,
    user_id: int,
    note: str | None = None,
    occurrences: int = 1,
) -> tuple[ReferenceSuggestion | None, str | None]:
    """Record that an unmatched value was accepted as an exception.

    An exception lives in this same table, distinguished by `status`, so a value
    cannot be pending and excepted at once and promoting one later reuses the
    resolve path unchanged.

    Returns `(row, warning)`. A warning is returned instead of a row when the
    value has already been decided — an already approved or rejected entry is
    never silently reopened as an exception.

    Called at **apply** time, in the same transaction as the rows that depend on
    it, so an abandoned review leaves nothing behind.
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
        if existing.status in {"ADDED", "MAPPED", "REJECTED"}:
            return None, (
                f"{entity_type.title()} '{raw_value}' has already been decided "
                f"({existing.status.lower()}). It was not reopened as an exception — "
                "re-run the import against the approved data."
            )
        existing.occurrence_count += occurrences
        existing.last_seen_at = now
        if existing.status != "EXCEPTION":
            # A pending entry the user has now decided about.
            existing.status = "EXCEPTION"
            existing.accepted_by_user_id = user_id
            existing.accepted_at = now
            if note:
                existing.exception_note = note
        # An existing exception keeps its original acceptance: the first
        # acceptance is the decision of record.
        session.flush()
        return existing, None

    row = ReferenceSuggestion(
        entity_type=entity_type,
        raw_value=raw_value,
        normalised_value=normalised,
        context=context,
        context_key=context_key,
        source=source,
        # How many rows depend on this exception, not how many times it was
        # accepted: the review counts the rows before writing (rule 1.9).
        occurrence_count=occurrences,
        first_seen_at=now,
        last_seen_at=now,
        status="EXCEPTION",
        accepted_by_user_id=user_id,
        accepted_at=now,
        exception_note=note,
    )
    session.add(row)
    session.flush()
    return row, None
