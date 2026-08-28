"""Resolve entries in the shared reference-suggestion queue.

The queue is not an allocation feature: every importer raises into it and every
reference-data tab reads from it. Resolving an entry must write the answer back
into the rows that raised it, so the database converges on a state where every
stored reference value is either an approved identifier, a recorded exception,
or a quarantined rejection.

Three administrator actions, plus one for exceptions:

* **Create / Map** — write the approved record's id into every affected row.
  They differ only in where the id came from; the write-back is identical.
* **Reject** — for the four structural entities the affected deliveries are
  *quarantined*, never deleted. For a classroom or trainer the identifier and
  text are cleared, returning the session to the ordinary "awaiting allocation"
  state the system already models.
* **Withdraw** — an accepted exception returns to the pending queue.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.enums import suggestion_entity_type
from app.models.allocation import AllocationDelivery, AllocationSession, ReferenceSuggestion
from app.models.user import User
from app.models.trainer import TrainerUnit
from app.services.activity import record_activity
from app.services.allocation_import import AllocationImportError

#: The four entities stored on `allocation_delivery`: (text column, id column, id name).
_DELIVERY_FIELDS = {
    "COLLEGE": (AllocationDelivery.college_text, AllocationDelivery.college_id, "college_id"),
    "CAMPUS": (AllocationDelivery.campus_text, AllocationDelivery.campus_id, "campus_id"),
    "QUALIFICATION": (
        AllocationDelivery.qualification_text,
        AllocationDelivery.qualification_id,
        "qualification_id",
    ),
    "UNIT": (AllocationDelivery.unit_text, AllocationDelivery.unit_id, "unit_id"),
}

#: The two entities a trainer's unit link can hold as text, since 27 August
#: 2026. Raising a suggestion on the trainer import lets the row in with the
#: raw value; resolving it here is what repairs the row.
_TRAINER_UNIT_FIELDS = {
    "QUALIFICATION": (
        TrainerUnit.qualification_text,
        TrainerUnit.qualification_id,
        "qualification_id",
    ),
    "UNIT": (TrainerUnit.unit_text, TrainerUnit.unit_id, "unit_id"),
}

#: The two entities stored on `allocation_session`.
_SESSION_FIELDS = {
    "FACILITY": (
        AllocationSession.classroom_text,
        AllocationSession.facility_id,
        "facility_id",
        "classroom_text",
    ),
    "TRAINER": (
        AllocationSession.trainer_text,
        AllocationSession.trainer_id,
        "trainer_id",
        "trainer_text",
    ),
}

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def _normalised(column):
    """The SQL equivalent of `reference_suggestions._normalise`.

    `btrim` alone is not enough: the Python normaliser collapses **internal**
    whitespace too, so `Rm  3B` and `Rm 3B` deduplicate into one entry. Without
    the same collapse here the resolution would silently miss every spelling
    that differed only by an inner space — the rows this work exists to repair.
    """
    return func.upper(func.btrim(func.regexp_replace(column, r"\s+", " ", "g")))


def _display_date(value: dt.datetime) -> str:
    """The approved DD-MMM-YYYY form, written out rather than locale-dependent."""
    return f"{value.day:02d}-{_MONTHS[value.month - 1]}-{value.year}"


def list_suggestions(
    session: Session,
    entity_type: str | None = None,
    status: str = "PENDING",
    entity_types: list[str] | None = None,
    limit: int | None = None,
    offset: int = 0,
) -> tuple[list[ReferenceSuggestion], int]:
    """Entries of one status, optionally narrowed to the entities a tab owns."""
    stmt = select(ReferenceSuggestion).where(ReferenceSuggestion.status == status)
    if entity_type:
        stmt = stmt.where(ReferenceSuggestion.entity_type == entity_type.upper())
    if entity_types:
        stmt = stmt.where(
            ReferenceSuggestion.entity_type.in_([value.upper() for value in entity_types])
        )
    total = session.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    stmt = stmt.order_by(
        ReferenceSuggestion.occurrence_count.desc(), ReferenceSuggestion.first_seen_at.desc()
    )
    if limit is not None:
        stmt = stmt.limit(limit).offset(max(offset, 0))
    return list(session.execute(stmt).scalars()), total


def summary(session: Session) -> list[dict]:
    """Pending and exception counts per entity type — **one** grouped query.

    Every tab indicator reads this. Calling the list endpoint once per entity
    merely to count would be six round trips for a number.
    """
    rows = session.execute(
        select(ReferenceSuggestion.entity_type, ReferenceSuggestion.status, func.count())
        .where(ReferenceSuggestion.status.in_(["PENDING", "EXCEPTION"]))
        .group_by(ReferenceSuggestion.entity_type, ReferenceSuggestion.status)
    ).all()

    counts: dict[str, dict[str, int]] = {}
    for entity_type, status, count in rows:
        entry = counts.setdefault(entity_type, {"pending": 0, "exceptions": 0})
        entry["pending" if status == "PENDING" else "exceptions"] = count

    # Every entity type is returned, including the ones with nothing to do, so a
    # tab can render a stable grey indicator rather than nothing at all.
    return [
        {
            "entity_type": name,
            "pending": counts.get(name, {}).get("pending", 0),
            "exceptions": counts.get(name, {}).get("exceptions", 0),
        }
        for name in suggestion_entity_type.enums
    ]


def resolve_suggestion(
    session: Session,
    user: User,
    *,
    suggestion_id: int,
    action: str,
    resolved_entity_id: int | None = None,
) -> tuple[ReferenceSuggestion, int]:
    """Apply an administrator's decision and return the rows it changed.

    The count is returned rather than discarded: a resolution that updates zero
    rows is exactly the condition that let the relink fault go unnoticed, and the
    interface must be able to say so instead of reporting a plain success.
    """
    row = session.get(ReferenceSuggestion, suggestion_id)
    if row is None:
        raise AllocationImportError("That suggestion was not found.")
    now = dt.datetime.now(dt.timezone.utc)
    action = action.upper()
    records_updated = 0

    if action in {"MAPPED", "MAP", "ADDED", "ADD", "CREATE", "CREATED"}:
        if not resolved_entity_id:
            raise AllocationImportError("Create or Map needs an approved record.")
        records_updated = _relink(session, row, resolved_entity_id)
        row.status = "MAPPED" if action in {"MAPPED", "MAP"} else "ADDED"
        row.resolved_entity_id = resolved_entity_id
        # `accepted_by_user_id` / `accepted_at` are deliberately retained: a
        # promoted exception must still show that it was once an exception and
        # who allowed it.
    elif action in {"DELETED", "REJECTED", "REJECT"}:
        records_updated = _reject(session, row, user, now)
        row.status = "REJECTED"
        row.resolved_entity_id = None
    elif action in {"WITHDRAW", "WITHDRAWN"}:
        if row.status != "EXCEPTION":
            raise AllocationImportError("Only an accepted exception can be withdrawn.")
        # The value returns to the queue for a proper decision. No stored row
        # changes — the dependent rows were already unresolved and stay so.
        row.status = "PENDING"
        row.accepted_by_user_id = None
        row.accepted_at = None
        row.resolved_entity_id = None
        row.resolved_by_user_id = None
        row.resolved_at = None
    else:
        raise AllocationImportError("Choose Create, Map, Reject or Withdraw.")

    if action not in {"WITHDRAW", "WITHDRAWN"}:
        row.resolved_by_user_id = user.id
        row.resolved_at = now

    session.flush()
    record_activity(
        session,
        user=user,
        action="UPDATE",
        page_or_function="Reference data - suggestion queue",
        detail=(
            f"{action.title()} {row.entity_type} suggestion '{row.raw_value}' — "
            f"{records_updated} record(s) updated."
        ),
        record_reference=str(row.id),
        result="COMPLETED",
    )
    return row, records_updated


def _relink(session: Session, suggestion: ReferenceSuggestion, entity_id: int) -> int:
    """Write the approved id into every row that raised this entry.

    Matching is on the **normalised** text, not the raw value. Deduplication
    already folds `Rm 3B`, `rm 3b` and `Rm  3B` into one entry, so comparing the
    raw value repaired only the one spelling stored on the entry and left the
    others unresolved with no queue entry left to find them by.

    The identifier must still be NULL, so a row already resolved that merely
    retains its text is not touched. The text itself is retained after a
    successful resolve — it records what the source file said.

    One `UPDATE` per entry, never one per row.
    """
    entity = suggestion.entity_type
    normalised = suggestion.normalised_value

    repaired = 0
    if entity in _DELIVERY_FIELDS:
        text_column, id_column, id_name = _DELIVERY_FIELDS[entity]
        result = session.execute(
            update(AllocationDelivery)
            .where(_normalised(text_column) == normalised, id_column.is_(None))
            .values(**{id_name: entity_id})
        )
        repaired += result.rowcount or 0
        if entity not in _TRAINER_UNIT_FIELDS:
            return repaired

    if entity in _TRAINER_UNIT_FIELDS:
        # A qualification or unit can be outstanding on both an allocation
        # delivery and a trainer's approved scope, so both are repaired and the
        # counts add up. Falls through from the delivery branch above, which
        # already returned for the allocation rows.
        text_column, id_column, id_name = _TRAINER_UNIT_FIELDS[entity]
        result = session.execute(
            update(TrainerUnit)
            .where(_normalised(text_column) == normalised, id_column.is_(None))
            .values(**{id_name: entity_id})
        )
        return repaired + (result.rowcount or 0)

    if entity in _SESSION_FIELDS:
        text_column, id_column, id_name, _text_name = _SESSION_FIELDS[entity]
        conditions = [_normalised(text_column) == normalised, id_column.is_(None)]
        if entity == "TRAINER":
            # An MSCRIS trainer is free text by approved decision (OD-11) and is
            # never linked to an approved trainer record.
            conditions.append(AllocationSession.stream != "MSCRIS")
        result = session.execute(
            update(AllocationSession).where(*conditions).values(**{id_name: entity_id})
        )
        return result.rowcount or 0

    raise AllocationImportError(f"{entity} cannot be relinked.")


def _reject(session: Session, suggestion: ReferenceSuggestion, user: User, now: dt.datetime) -> int:
    """Reject a value: quarantine for structural entities, clear for the rest."""
    entity = suggestion.entity_type
    normalised = suggestion.normalised_value

    if entity in _DELIVERY_FIELDS:
        # Approved 26 August 2026: rejecting retains the rows. They are marked,
        # excluded from every operational view, and stay visible to an
        # administrator so a mistaken rejection can be undone.
        text_column, _id_column, _id_name = _DELIVERY_FIELDS[entity]
        reason = (
            f"{entity.title()} '{suggestion.raw_value}' was rejected on "
            f"{_display_date(now)} by {user.organisation_email}."
        )
        result = session.execute(
            update(AllocationDelivery)
            .where(
                _normalised(text_column) == normalised,
                AllocationDelivery.is_quarantined.is_(False),
            )
            .values(
                is_quarantined=True,
                quarantine_reason=reason,
                quarantined_at=now,
                quarantined_by_user_id=user.id,
            )
        )
        return result.rowcount or 0

    if entity in _SESSION_FIELDS:
        # Quarantining a session because its classroom name was rejected would
        # hide a legitimate class that simply needs a room assigned. Clear it
        # instead and let it show as awaiting allocation.
        text_column, id_column, id_name, text_name = _SESSION_FIELDS[entity]
        conditions = [
            _normalised(text_column) == normalised,
            # The guard that was missing: without it, rejecting a value blanked
            # the identifier on sessions that were already correctly resolved and
            # merely retained the text.
            id_column.is_(None),
        ]
        if entity == "TRAINER":
            conditions.append(AllocationSession.stream != "MSCRIS")
        result = session.execute(
            update(AllocationSession).where(*conditions).values(**{id_name: None, text_name: None})
        )
        return result.rowcount or 0

    raise AllocationImportError(f"{entity} cannot be rejected.")


def clear_quarantine_for(session: Session, suggestion: ReferenceSuggestion) -> int:
    """Lift the quarantine when a rejected value is raised again.

    A rejection that turns out to be a mistake is recoverable: re-importing the
    value returns the entry to PENDING, and the rows it covers come back with it.
    """
    if suggestion.entity_type not in _DELIVERY_FIELDS:
        return 0
    text_column, _id_column, _id_name = _DELIVERY_FIELDS[suggestion.entity_type]
    result = session.execute(
        update(AllocationDelivery)
        .where(
            _normalised(text_column) == suggestion.normalised_value,
            AllocationDelivery.is_quarantined.is_(True),
        )
        .values(
            is_quarantined=False,
            quarantine_reason=None,
            quarantined_at=None,
            quarantined_by_user_id=None,
        )
    )
    return result.rowcount or 0


def affected_records(session: Session, suggestion_id: int, limit: int = 50) -> dict:
    """The rows an entry affects — count plus a capped sample, in one query each.

    Rule 1.4 asks for each entry to be linked to everywhere it affects. The
    dialog shows the count on the entry and fetches this list only on demand, so
    opening the dialog never costs one query per entry.
    """
    suggestion = session.get(ReferenceSuggestion, suggestion_id)
    if suggestion is None:
        raise AllocationImportError("That suggestion was not found.")

    entity = suggestion.entity_type
    normalised = suggestion.normalised_value

    if entity in _DELIVERY_FIELDS:
        text_column, id_column, _id_name = _DELIVERY_FIELDS[entity]
        condition = (_normalised(text_column) == normalised) & id_column.is_(None)
        total = session.execute(
            select(func.count()).select_from(AllocationDelivery).where(condition)
        ).scalar_one()
        rows = session.execute(
            select(AllocationDelivery).where(condition).order_by(AllocationDelivery.id).limit(limit)
        ).scalars()
        items = [
            {
                "kind": "delivery",
                "id": row.id,
                "training_package": row.training_package,
                "college": row.college_text,
                "campus": row.campus_text,
                "qualification_code": row.qualification_text,
                "unit_code": row.unit_text,
                "group_code": row.group_code,
                "start_date": row.start_date.isoformat(),
                "end_date": row.end_date.isoformat(),
                "is_quarantined": row.is_quarantined,
            }
            for row in rows
        ]
    elif entity in _SESSION_FIELDS:
        text_column, id_column, _id_name, _text_name = _SESSION_FIELDS[entity]
        condition = (_normalised(text_column) == normalised) & id_column.is_(None)
        total = session.execute(
            select(func.count()).select_from(AllocationSession).where(condition)
        ).scalar_one()
        rows = session.execute(
            select(AllocationSession).where(condition).order_by(AllocationSession.id).limit(limit)
        ).scalars()
        items = [
            {
                "kind": "session",
                "id": row.id,
                "training_package": row.training_package,
                "stream": row.stream,
                "weekday": row.weekday,
                "classroom": row.classroom_text,
                "trainer": row.trainer_text,
                "delivery_id": row.delivery_id,
            }
            for row in rows
        ]
    else:  # pragma: no cover - guarded by the entity enum
        total, items = 0, []

    return {
        "suggestion_id": suggestion_id,
        "entity_type": entity,
        "raw_value": suggestion.raw_value,
        "total": total,
        "items": items,
        "truncated": total > len(items),
    }
