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
import difflib

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.orm import Session

from app.db.enums import suggestion_entity_type
from app.models.allocation import AllocationDelivery, AllocationSession, ReferenceSuggestion
from app.models.user import User
from app.models.qualification import Qualification, QualificationUnit, Unit
from app.models.student import Student
from app.models.college import Campus, CampusSourceAddress, College, CollegeCampus
from app.models.facility import Facility
from app.models.trainer import Trainer, TrainerUnit
from app.services.activity import record_activity
from app.services.allocation_import import AllocationImportError

#: What a student holds unverified. Unlike the others this has no matching id
#: column: a student's college, campus and qualification are reached through
#: `course_offering_id`, which is derived from all three at once. So a student is
#: not repaired field by field - it is *completed* once every one of its texts
#: resolves. See `_complete_students`.
_STUDENT_TEXT = {
    "COLLEGE": Student.college_text,
    "CAMPUS": Student.campus_text,
    "QUALIFICATION": Student.qualification_text,
}

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


def _rolling_unit_rows(session: Session, normalised_value: str, qualification_code: str) -> int:
    """Stored rolling-timetable rows naming this unit under this qualification.

    `rolling_timetable_weeks` holds `qualification_code` and `unit_code` as text
    with no foreign keys, so every row is unresolved by construction. What makes
    one *outstanding* is that Qualification Data does not list the unit for that
    qualification - the rolling timetable orders what belongs, it does not decide
    what belongs, so a unit it names that the source file omits is a real gap
    somebody has to close.

    Counting these is what lets such an entry satisfy the queue rule: it has
    stored rows behind it, and the moment the membership link exists the count
    falls to zero and the entry closes itself.
    """
    if not qualification_code:
        return 0
    return session.execute(
        text(
            # Raw string: the SQL contains `\s`, which is a regex escape for
            # PostgreSQL, not a Python one.
            r"""
            SELECT count(*)
              FROM rolling_timetable_weeks w
              LEFT JOIN units u
                     ON upper(btrim(regexp_replace(u.unit_code, '\s+', ' ', 'g'))) = :unit
              LEFT JOIN qualifications q
                     ON upper(btrim(regexp_replace(q.qualification_code, '\s+', ' ', 'g'))) = :qual
              LEFT JOIN qualification_units qu
                     ON qu.qualification_id = q.id AND qu.unit_id = u.id
             WHERE w.schedule_type = 'UNIT'
               AND upper(btrim(regexp_replace(w.unit_code, '\s+', ' ', 'g'))) = :unit
               AND upper(btrim(regexp_replace(w.qualification_code, '\s+', ' ', 'g'))) = :qual
               AND qu.id IS NULL
            """
        ),
        {"unit": normalised_value, "qual": qualification_code.strip().upper()},
    ).scalar_one()


def unresolved_total(
    session: Session,
    entity_type: str,
    normalised_value: str,
    context: dict | None = None,
) -> int:
    """How many stored rows still carry this value unresolved, across every table.

    The single source of truth for "does this entry still have anything behind
    it". Everything that asks the question - the count on an entry, the affected
    list, the prune - must ask it here, or they disagree and the interface starts
    contradicting itself.

    Before this existed, the count looked at `allocation_delivery` and
    `allocation_session` only, while the repair also wrote `trainer_units`. A
    unit suggestion therefore reported fewer rows than resolving it would fix,
    and a prune driven by that number would have deleted entries with live
    trainer rows behind them.
    """
    total = 0

    if entity_type in _DELIVERY_FIELDS:
        text_column, id_column, _ = _DELIVERY_FIELDS[entity_type]
        total += session.execute(
            select(func.count())
            .select_from(AllocationDelivery)
            .where(_normalised(text_column) == normalised_value, id_column.is_(None))
        ).scalar_one()

    if entity_type in _TRAINER_UNIT_FIELDS:
        text_column, id_column, _ = _TRAINER_UNIT_FIELDS[entity_type]
        total += session.execute(
            select(func.count())
            .select_from(TrainerUnit)
            .where(_normalised(text_column) == normalised_value, id_column.is_(None))
        ).scalar_one()

    if entity_type in _SESSION_FIELDS:
        text_column, id_column, _, _ = _SESSION_FIELDS[entity_type]
        conditions = [_normalised(text_column) == normalised_value, id_column.is_(None)]
        if entity_type == "TRAINER":
            # An MSCRIS trainer is free text by approved decision (OD-11) and is
            # never linked, so those rows are not waiting on this entry and must
            # not keep it alive.
            conditions.append(AllocationSession.stream != "MSCRIS")
        total += session.execute(
            select(func.count()).select_from(AllocationSession).where(*conditions)
        ).scalar_one()

    # A UNIT entry whose context names a qualification is asking for membership,
    # not for an identifier: the unit may exist perfectly well and simply not be
    # listed under that qualification.
    if entity_type == "UNIT" and context:
        total += _rolling_unit_rows(session, normalised_value, str(context.get("qualification") or ""))

    if entity_type in _STUDENT_TEXT:
        text_column = _STUDENT_TEXT[entity_type]
        total += session.execute(
            select(func.count())
            .select_from(Student)
            .where(
                _normalised(text_column) == normalised_value,
                Student.course_offering_id.is_(None),
                Student.is_deleted.is_(False),
            )
        ).scalar_one()

    return total


def prune_empty(session: Session) -> list[dict]:
    """Remove open entries with nothing behind them, and report what went.

    The approved rule (8 September 2026): an entry exists exactly while some
    stored row still carries its value unresolved. Nothing behind it means there
    is nothing to decide, and leaving it offers an administrator a choice that
    changes nothing.

    Only `PENDING` and `EXCEPTION` are considered. A `MAPPED`, `ADDED` or
    `REJECTED` entry is a decision someone made and is kept as the record of it.

    Deleting is safe precisely because the entry is derived: if the value
    returns - the file is imported again, or another file names it - the import
    raises it afresh, against rows that actually exist.
    """
    removed: list[dict] = []
    rows = session.execute(
        select(ReferenceSuggestion).where(ReferenceSuggestion.status.in_(("PENDING", "EXCEPTION")))
    ).scalars()
    for row in rows:
        if unresolved_total(session, row.entity_type, row.normalised_value, row.context) > 0:
            continue
        removed.append(
            {
                "id": row.id,
                "entity_type": row.entity_type,
                "raw_value": row.raw_value,
                "status": row.status,
                "source": row.source,
                "occurrence_count": row.occurrence_count,
            }
        )
        session.delete(row)
    return removed


def resolve_suggestion(
    session: Session,
    user: User,
    *,
    suggestion_id: int,
    action: str,
    resolved_entity_id: int | None = None,
    create_values: dict[str, str] | None = None,
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

    if action in {"ADDED", "ADD", "CREATE", "CREATED"} and not resolved_entity_id:
        # Create brings the record into existence, then resolves onto it.
        #
        # Until now Create demanded an existing record exactly as Map did, so it
        # was Map under another name and a value that existed nowhere had no way
        # through the interface at all - the three units a rolling timetable
        # named but no file listed had to be added with a script.
        resolved_entity_id = _create_entity(session, row, create_values or {})

    if action in {"MAPPED", "MAP", "ADDED", "ADD", "CREATE", "CREATED"}:
        if not resolved_entity_id:
            raise AllocationImportError("Create or Map needs an approved record.")
        records_updated = _relink(session, row, resolved_entity_id)
        # After the relink, never before: the relink finds its rows by the
        # misspelled text, so rewriting that text first would leave it nothing
        # to match.
        corrected = _correct_spelling(session, row, resolved_entity_id)
        records_updated = max(records_updated, corrected)
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


def _create_entity(
    session: Session, suggestion: ReferenceSuggestion, values: dict[str, str]
) -> int:
    """Bring the record an entry names into existence, and return its id.

    The entry supplies the identifier - it is the value that failed to resolve -
    and `values` supplies everything else the table requires. Nothing is
    invented: a unit named only by a rolling timetable has no title anywhere in
    TDMS, because the timetable stores the code twice and no name, so the title
    is asked for.

    A code that already exists is reused rather than duplicated. `units.unit_code`
    is globally unique, so a second row is impossible anyway, and for a
    membership entry this is the ordinary case: the unit exists, it just does
    not belong to this qualification yet.
    """
    raw = (suggestion.raw_value or "").strip()
    if not raw:
        raise AllocationImportError("This entry has no value to create a record from.")

    if suggestion.entity_type != "UNIT":
        raise AllocationImportError(
            f"Creating a {suggestion.entity_type.title()} from the queue is not built yet. "
            "Add the record in its own tab, then map this entry to it."
        )

    existing = session.execute(
        select(Unit).where(func.upper(func.btrim(Unit.unit_code)) == raw.upper())
    ).scalars().first()
    if existing is not None:
        return existing.id

    title = (values.get("unit_title") or "").strip()
    if not title:
        raise AllocationImportError(f"{raw} is a new unit. Its title is needed to create it.")

    unit = Unit(unit_code=raw, unit_title=title, is_active=True)
    session.add(unit)
    session.flush()
    return unit.id


def _link_membership(session: Session, suggestion: ReferenceSuggestion, unit_id: int) -> int:
    """Add the unit to the qualification its entry names, if it is not there.

    A UNIT entry raised from a rolling timetable is not saying "this unit does
    not exist" - it usually does. It is saying Qualification Data does not list
    it for that qualification, and the timetable teaches it there. Resolving it
    is therefore a membership decision, and the repair is a
    `qualification_units` row rather than an identifier written into a text
    column.

    `delivery_order` is left NULL. The position comes from a rolling timetable
    through the reference import, which is the one place allowed to write it;
    inventing one here would put an unapproved sequence in the same column an
    approved one lives in.

    Returns the number of rolling-timetable rows the link accounts for, so the
    caller reports the size of what was fixed rather than the single row written.
    """
    code = str((suggestion.context or {}).get("qualification") or "").strip()
    if not code:
        return 0

    qualification = session.execute(
        select(Qualification).where(
            func.upper(func.btrim(Qualification.qualification_code)) == code.upper()
        )
    ).scalars().first()
    if qualification is None:
        raise AllocationImportError(
            f"{code} is not an approved qualification, so the unit cannot be added to it."
        )

    covered = _rolling_unit_rows(session, suggestion.normalised_value, code)

    existing = session.execute(
        select(QualificationUnit).where(
            QualificationUnit.qualification_id == qualification.id,
            QualificationUnit.unit_id == unit_id,
        )
    ).scalars().first()
    if existing is None:
        session.add(
            QualificationUnit(
                qualification_id=qualification.id, unit_id=unit_id, delivery_order=None
            )
        )
        session.flush()
    return covered


def _relink(session: Session, suggestion: ReferenceSuggestion, entity_id: int) -> int:
    """Write the approved id into every row that raised this entry.

    Matching is on the **normalised** text, not the raw value. Deduplication
    already folds `Rm 3B`, `rm 3b` and `Rm  3B` into one entry, so comparing the
    raw value repaired only the one spelling stored on the entry and left the
    others unresolved with no queue entry left to find them by.

    The identifier must still be NULL, so a row already resolved that merely
    retains its text is not touched. The misspelled text is corrected afterwards
    by `_correct_spelling`, not here.

    One `UPDATE` per entry, never one per row.
    """
    entity = suggestion.entity_type
    normalised = suggestion.normalised_value

    repaired = 0
    if entity == "UNIT" and (suggestion.context or {}).get("qualification"):
        repaired += _link_membership(session, suggestion, entity_id)
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
        items = []

    # A membership entry's rows live in `rolling_timetable_weeks`, which the
    # branches above do not read - so the count said 192 and the list showed
    # nothing. Summarised by intake rather than listed week by week: 192 rows is
    # eight intakes teaching the unit, and eight lines say that where 192 do not.
    if entity == "UNIT" and (suggestion.context or {}).get("qualification"):
        code = str(suggestion.context["qualification"]).strip().upper()
        rolling = session.execute(
            text(
                # Raw string: `\s` here is a PostgreSQL regex escape.
                r"""
                SELECT w.intake_label,
                       w.duration_weeks,
                       count(*)          AS week_rows,
                       min(w.week_no)    AS first_week,
                       max(w.week_no)    AS last_week
                  FROM rolling_timetable_weeks w
                 WHERE w.schedule_type = 'UNIT'
                   AND upper(btrim(regexp_replace(w.unit_code, '\s+', ' ', 'g'))) = :unit
                   AND upper(btrim(regexp_replace(w.qualification_code, '\s+', ' ', 'g'))) = :qual
                 GROUP BY w.intake_label, w.duration_weeks
                 ORDER BY w.intake_label
                 LIMIT :limit
                """
            ),
            {"unit": normalised, "qual": code, "limit": limit},
        )
        items = [
            {
                "kind": "rolling_intake",
                "intake_label": row.intake_label,
                "duration_weeks": row.duration_weeks,
                "week_rows": row.week_rows,
                "first_week": row.first_week,
                "last_week": row.last_week,
            }
            for row in rolling
        ] + items

    # The total counts every table the repair touches, not just the one the
    # sample was drawn from. The sample stays a sample of allocation rows -
    # trainer units and students are counted but not listed, because their
    # shapes do not fit these columns - so `truncated` is what tells the reader
    # the list is shorter than the count.
    total = unresolved_total(session, entity, normalised, suggestion.context)

    return {
        "suggestion_id": suggestion_id,
        "entity_type": entity,
        "raw_value": suggestion.raw_value,
        "total": total,
        "items": items,
        "truncated": total > len(items),
    }


# ---------------------------------------------------------------------------
# Map options
# ---------------------------------------------------------------------------

#: A spelling this close to the raw value is listed first whatever its scope. A
#: membership entry - a unit a rolling timetable teaches under a qualification
#: that does not list it - is raised *because* the unit is outside that
#: qualification, so ranking scope first would bury the exact unit beneath every
#: unit the qualification already has.
_CLOSE_SPELLING = 0.85


def _plain(value: object) -> str:
    """The queue's normaliser in Python: collapsed whitespace, upper case."""
    return " ".join(str(value or "").split()).upper()


def _college_named(session: Session, name: object) -> College | None:
    key = _plain(name)
    if not key:
        return None
    for college in session.execute(select(College)).scalars():
        if key in (_plain(college.college_short_name), _plain(college.college_full_name)):
            return college
    return None


def _campus_named(session: Session, name: object) -> Campus | None:
    """A campus by name, code, address, or any spelling recorded for it."""
    key = _plain(name)
    if not key:
        return None
    for campus in session.execute(select(Campus)).scalars():
        if key in (_plain(campus.campus_name), _plain(campus.campus_code), _plain(campus.campus_location)):
            return campus
    alias = session.execute(
        select(CampusSourceAddress).where(_normalised(CampusSourceAddress.source_address) == key)
    ).scalars().first()
    return session.get(Campus, alias.campus_id) if alias is not None else None


def _qualification_coded(session: Session, code: object) -> Qualification | None:
    key = _plain(code)
    if not key:
        return None
    return session.execute(
        select(Qualification).where(func.upper(func.btrim(Qualification.qualification_code)) == key)
    ).scalars().first()


def map_options(
    session: Session, suggestion_id: int, *, search: str | None = None, limit: int = 50
) -> dict:
    """The records an entry could be mapped to, narrowed by what it was raised with.

    Map means "this value is another spelling of a record we already have", so
    the useful list is not every record of that type - it is the records the
    value could plausibly mean. The entry's context says where it was seen, and
    that decides the scope:

    * **UNIT** under a qualification: that qualification's units first.
    * **FACILITY** at a campus: rooms at that campus *only*. A room is unique
      within its campus, so a room elsewhere cannot be the same room - and before
      this every `Room 3` in the system was offered with nothing saying where.
    * **CAMPUS** for a college: the locations that college operates first.
    * **COLLEGE**, **QUALIFICATION**, **TRAINER**: no narrowing context is raised
      with them, so every active record, closest spelling first.

    Ranking is by closeness of spelling to the raw value. That is safe here in a
    way it is not for automatic resolution: a person reads the list and chooses,
    so the ordering only decides what they see first, never what is applied.
    """
    row = session.get(ReferenceSuggestion, suggestion_id)
    if row is None:
        raise AllocationImportError("That suggestion was not found.")

    entity = row.entity_type
    context = row.context or {}
    scope_label: str | None = None
    scope_id: int | None = None
    scope_only = False
    in_scope: set[int] = set()
    candidates: list[dict] = []

    def offer(record_id: int, label: str, texts: tuple, detail: str | None = None) -> None:
        candidates.append({"id": record_id, "label": label, "detail": detail, "texts": texts})

    if entity == "COLLEGE":
        for college in session.execute(select(College).where(College.is_active.is_(True))).scalars():
            offer(
                college.id,
                f"{college.college_short_name} — {college.college_full_name}",
                (college.college_short_name, college.college_full_name),
            )

    elif entity == "CAMPUS":
        college = _college_named(session, context.get("college"))
        if college is not None:
            scope_label = f"Locations {college.college_short_name} operates"
            scope_id = college.id
            in_scope = set(
                session.execute(
                    select(CollegeCampus.campus_id).where(CollegeCampus.college_id == college.id)
                ).scalars()
            )
        for campus in session.execute(select(Campus).where(Campus.is_active.is_(True))).scalars():
            offer(
                campus.id,
                f"{campus.campus_name} — {campus.campus_location}",
                (campus.campus_name, campus.campus_code, campus.campus_location),
            )

    elif entity == "QUALIFICATION":
        for qualification in session.execute(
            select(Qualification).where(Qualification.is_active.is_(True))
        ).scalars():
            code = qualification.qualification_code or "NA"
            offer(
                qualification.id,
                f"{code} — {qualification.qualification_title}",
                (qualification.qualification_code, qualification.qualification_title),
            )

    elif entity == "UNIT":
        qualification = _qualification_coded(session, context.get("qualification"))
        if qualification is not None:
            scope_label = f"Units of {qualification.qualification_code}"
            scope_id = qualification.id
            in_scope = set(
                session.execute(
                    select(QualificationUnit.unit_id).where(
                        QualificationUnit.qualification_id == qualification.id
                    )
                ).scalars()
            )
        for unit in session.execute(select(Unit).where(Unit.is_active.is_(True))).scalars():
            offer(unit.id, f"{unit.unit_code} — {unit.unit_title}", (unit.unit_code, unit.unit_title))

    elif entity == "FACILITY":
        campus = _campus_named(session, context.get("campus"))
        statement = select(Facility).where(Facility.is_active.is_(True))
        if campus is not None:
            scope_label = f"Rooms at {campus.campus_name}"
            scope_id = campus.id
            scope_only = True
            statement = statement.where(Facility.campus_id == campus.id)
        for facility in session.execute(statement).scalars():
            offer(
                facility.id,
                f"{facility.facility_reference} — {facility.campus.campus_name}",
                (facility.facility_reference,),
                detail=facility.source_location or None,
            )
            if campus is not None:
                in_scope.add(facility.id)

    elif entity == "TRAINER":
        for trainer in session.execute(select(Trainer).where(Trainer.is_deleted.is_(False))).scalars():
            offer(
                trainer.id,
                f"{trainer.trainer_id} — {trainer.trainer_name}",
                (trainer.trainer_name, trainer.trainer_id),
            )

    needle = _plain(search)
    target = _plain(row.raw_value)
    ranked: list[dict] = []
    for candidate in candidates:
        texts = [_plain(value) for value in candidate["texts"] if value]
        if needle and not any(needle in value for value in texts):
            continue
        closeness = max(
            (difflib.SequenceMatcher(None, target, value).ratio() for value in texts),
            default=0.0,
        )
        ranked.append(
            {
                "id": candidate["id"],
                "label": candidate["label"],
                "detail": candidate["detail"],
                "in_scope": candidate["id"] in in_scope,
                "_closeness": closeness,
            }
        )

    ranked.sort(
        key=lambda item: (
            item["_closeness"] < _CLOSE_SPELLING,
            not item["in_scope"],
            -item["_closeness"],
            item["label"],
        )
    )
    return {
        "suggestion_id": row.id,
        "entity_type": entity,
        "scope_label": scope_label,
        "scope_id": scope_id,
        "scope_only": scope_only,
        "items": [
            {key: value for key, value in item.items() if key != "_closeness"}
            for item in ranked[:limit]
        ],
        "total": len(ranked),
        "truncated": len(ranked) > limit,
    }


def _canonical_spelling(session: Session, entity: str, entity_id: int) -> str | None:
    """How the approved record spells the value an entry was resolved to."""
    if entity == "COLLEGE":
        record = session.get(College, entity_id)
        return record.college_short_name if record else None
    if entity == "CAMPUS":
        record = session.get(Campus, entity_id)
        return record.campus_name if record else None
    if entity == "QUALIFICATION":
        record = session.get(Qualification, entity_id)
        return (record.qualification_code or record.qualification_title) if record else None
    if entity == "UNIT":
        record = session.get(Unit, entity_id)
        return record.unit_code if record else None
    if entity == "FACILITY":
        record = session.get(Facility, entity_id)
        return record.facility_reference if record else None
    if entity == "TRAINER":
        record = session.get(Trainer, entity_id)
        return record.trainer_name if record else None
    return None


def _correct_spelling(session: Session, suggestion: ReferenceSuggestion, entity_id: int) -> int:
    """Rewrite a resolved value to the approved spelling everywhere it is stored.

    Approved 14 September 2026: mapping a misspelling corrects it everywhere.
    Before this, the relink wrote the identifier and left the text as the source
    spelled it. Where a table has an identifier that was enough to resolve the
    row - but `rolling_timetable_weeks` has none. A unit misspelled there kept
    its misspelling, still matched no unit, and so the entry never closed and
    was answered again on every import.

    A row is corrected only when it is unresolved or already resolved to this
    same record. A row resolved to a *different* record that happens to share
    the text is left alone - rewriting it would put one record's spelling on
    another record's row.

    MSCRIS sessions are skipped for trainers: their trainer is free text by
    approved decision (OD-11) and is never linked, so it is not this entry's to
    change.

    A re-import of a source file that still carries the misspelling will raise
    it again. That is correct - the fix belongs in the file too - and it arrives
    as a fresh entry against real rows rather than a silent reversal.

    Returns the number of rows whose text changed.
    """
    entity = suggestion.entity_type
    normalised = suggestion.normalised_value
    canonical = _canonical_spelling(session, entity, entity_id)
    if not canonical or _plain(canonical) == normalised:
        return 0

    corrected = 0

    if entity in _DELIVERY_FIELDS:
        text_column, id_column, _id_name = _DELIVERY_FIELDS[entity]
        result = session.execute(
            update(AllocationDelivery)
            .where(
                _normalised(text_column) == normalised,
                or_(id_column.is_(None), id_column == entity_id),
            )
            .values(**{text_column.key: canonical})
        )
        corrected += result.rowcount or 0

    if entity in _TRAINER_UNIT_FIELDS:
        text_column, id_column, _id_name = _TRAINER_UNIT_FIELDS[entity]
        result = session.execute(
            update(TrainerUnit)
            .where(
                _normalised(text_column) == normalised,
                or_(id_column.is_(None), id_column == entity_id),
            )
            .values(**{text_column.key: canonical})
        )
        corrected += result.rowcount or 0

    if entity in _SESSION_FIELDS:
        text_column, id_column, _id_name, text_name = _SESSION_FIELDS[entity]
        conditions = [
            _normalised(text_column) == normalised,
            or_(id_column.is_(None), id_column == entity_id),
        ]
        if entity == "TRAINER":
            conditions.append(AllocationSession.stream != "MSCRIS")
        result = session.execute(
            update(AllocationSession).where(*conditions).values(**{text_name: canonical})
        )
        corrected += result.rowcount or 0

    if entity in _STUDENT_TEXT:
        text_column = _STUDENT_TEXT[entity]
        result = session.execute(
            update(Student)
            .where(_normalised(text_column) == normalised)
            .values(**{text_column.key: canonical})
        )
        corrected += result.rowcount or 0

    if entity == "UNIT":
        # No identifier column, so the text is the only link to the unit. The
        # unit code is not part of the rolling timetable's unique key, so the
        # rewrite cannot collide with another row.
        result = session.execute(
            text(
                r"""
                UPDATE rolling_timetable_weeks
                   SET unit_code = :canonical,
                       schedule_value = CASE
                           WHEN upper(btrim(regexp_replace(schedule_value, '\s+', ' ', 'g'))) = :raw
                           THEN :canonical
                           ELSE schedule_value
                       END
                 WHERE schedule_type = 'UNIT'
                   AND upper(btrim(regexp_replace(unit_code, '\s+', ' ', 'g'))) = :raw
                """
            ),
            {"canonical": canonical, "raw": normalised},
        )
        corrected += result.rowcount or 0

    return corrected
