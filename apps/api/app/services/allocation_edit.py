"""Edit one allocation session. Same validator as import."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.allocation import AllocationDelivery, AllocationSession
from app.models.facility import Facility
from app.models.trainer import Trainer
from app.models.user import User
from app.services.activity import record_activity
from app.services import allocation_rules as rules
from app.services.allocation_import import AllocationImportError, _raise_or_count_suggestion, _upsert_suggestions


class AllocationEditError(AllocationImportError):
    pass


def _session_row(session: Session, session_id: int, training_package: str) -> AllocationSession:
    row = session.execute(
        select(AllocationSession).where(
            AllocationSession.id == session_id,
            AllocationSession.training_package == training_package.upper(),
        )
    ).scalar_one_or_none()
    if row is None:
        raise AllocationEditError("That class day was not found.")
    return row


def validate_session_change(
    row: AllocationSession,
    *,
    weekday: str,
    start_time: dt.time,
    end_time: dt.time,
    classroom: str | None,
    trainer: str | None,
) -> None:
    if weekday not in rules.allowed_weekdays(row.stream):
        raise AllocationEditError(f"{row.stream} cannot run on {weekday}.")
    if end_time <= start_time:
        raise AllocationEditError("The class must end after it starts.")
    if classroom and rules.virtual_kind_for(classroom) and not rules.stream_may_be_virtual(row.stream):
        raise AllocationEditError("A virtual value in a practical classroom column is refused — practical is never virtual.")
    if row.stream == "MSCRIS" and weekday != rules.MSCRIS_WEEKDAY:
        raise AllocationEditError("MSCRIS is Saturday and virtual.")


def update_session(
    session: Session,
    user: User,
    *,
    session_id: int,
    training_package: str,
    weekday: str,
    start_time: dt.time,
    end_time: dt.time,
    classroom: str | None,
    trainer: str | None,
    facility_id: int | None = None,
    trainer_id: int | None = None,
    log: bool = True,
) -> AllocationSession:
    row = _session_row(session, session_id, training_package)
    weekday = weekday.upper()
    validate_session_change(row, weekday=weekday, start_time=start_time, end_time=end_time, classroom=classroom, trainer=trainer)
    delivery = session.execute(
        select(AllocationDelivery).where(
            AllocationDelivery.id == row.delivery_id,
            AllocationDelivery.training_package == row.training_package,
        )
    ).scalar_one()
    siblings = list(
        session.execute(
            select(AllocationSession).where(
                AllocationSession.delivery_id == row.delivery_id,
                AllocationSession.training_package == row.training_package,
            )
        ).scalars()
    )
    teaching = rules.teaching_day_count(
        [(item.stream, weekday if item.id == row.id else item.weekday) for item in siblings]
    )
    changes = []
    if row.weekday != weekday:
        changes.append(f"weekday {row.weekday} → {weekday}")
        row.weekday = weekday
    if row.start_time != start_time or row.end_time != end_time:
        changes.append(f"time {row.start_time}–{row.end_time} → {start_time}–{end_time}")
        row.start_time = start_time
        row.end_time = end_time
    virtual_kind = rules.virtual_kind_for(classroom or "")
    if virtual_kind:
        row.delivery_mode = "VIRTUAL"
        row.facility_id = None
        row.virtual_kind = virtual_kind
        row.classroom_text = rules.CANONICAL_VIRTUAL_CLASSROOM
        changes.append(f"classroom → {classroom}")
    elif classroom:
        facility = session.get(Facility, facility_id) if facility_id is not None else session.execute(
            select(Facility).where(func.upper(Facility.facility_reference) == classroom.strip().upper()).limit(1)
        ).scalar_one_or_none()
        if facility:
            row.facility_id = facility.id
            row.delivery_mode = "PHYSICAL"
            row.virtual_kind = None
            row.classroom_text = classroom
        else:
            row.facility_id = None
            row.delivery_mode = "PHYSICAL"
            row.classroom_text = classroom
            suggestions = {}
            _raise_or_count_suggestion(
                suggestions,
                "FACILITY",
                classroom,
                {"qualification": str(delivery.qualification_id), "unit": str(delivery.unit_id)},
            )
            _upsert_suggestions(session, suggestions, dt.datetime.now(dt.timezone.utc))
        changes.append(f"classroom → {classroom}")
    if trainer is not None:
        found = session.get(Trainer, trainer_id) if trainer_id is not None else session.execute(
            select(Trainer).where(Trainer.trainer_name == trainer)
        ).scalar_one_or_none()
        if row.stream == "MSCRIS":
            row.trainer_id = None
            row.trainer_text = trainer or None
        elif found:
            row.trainer_id = found.id
            row.trainer_text = trainer
        else:
            row.trainer_text = trainer or None
            row.trainer_id = None
            if trainer:
                suggestions = {}
                _raise_or_count_suggestion(suggestions, "TRAINER", trainer, {"unit": str(delivery.unit_id)})
                _upsert_suggestions(session, suggestions, dt.datetime.now(dt.timezone.utc))
        changes.append(f"trainer → {trainer or 'unallocated'}")
    session.flush()
    warning = ""
    if teaching != rules.TEACHING_DAYS_PER_WEEK:
        warning = f" This unit now runs on {teaching} teaching day(s) a week."
    if not log:
        return row
    record_activity(
        session,
        user=user,
        action="UPDATE",
        page_or_function="Page 1 - Timetable View and Management",
        detail=f"Updated allocation session {row.id}: {'; '.join(changes) or 'no field change'}.{warning}",
        record_reference=str(row.id),
        result="COMPLETED",
    )
    return row


def update_mscris_group(
    session: Session,
    user: User,
    *,
    session_ids: list[int],
    training_package: str,
    start_time: dt.time,
    end_time: dt.time,
    classroom: str | None,
    trainer: str | None,
) -> int:
    """Edit a merged MSCRIS entry: every class day it covers changes together.

    Approved 17 September 2026. The entry is one class, so its time, classroom
    and trainer cannot differ between the units it covers. The caller's
    transaction makes it all or nothing: one refusal leaves every class day as it was.
    """
    ids = sorted(set(session_ids))
    rows = list(
        session.execute(
            select(AllocationSession).where(
                AllocationSession.id.in_(ids),
                AllocationSession.training_package == training_package.upper(),
            )
        ).scalars()
    )
    if len(rows) != len(ids):
        raise AllocationEditError("Some of these MSCRIS class days were not found. Reload and try again.")
    if any(row.stream != "MSCRIS" for row in rows):
        raise AllocationEditError("Only MSCRIS class days can be edited together.")
    for row in rows:
        update_session(
            session,
            user,
            session_id=row.id,
            training_package=training_package,
            weekday=row.weekday,
            start_time=start_time,
            end_time=end_time,
            classroom=classroom,
            trainer=trainer,
            log=False,
        )
    record_activity(
        session,
        user=user,
        action="UPDATE",
        page_or_function="Page 1 - Timetable View and Management",
        detail=(
            f"Updated an MSCRIS class covering {len(rows)} class day(s): "
            f"time {start_time:%H:%M}–{end_time:%H:%M}"
            + (f"; classroom → {classroom}" if classroom else "")
            + (f"; trainer → {trainer or 'unallocated'}" if trainer is not None else "")
            + "."
        ),
        record_reference=",".join(str(row.id) for row in rows)[:500],
        result="COMPLETED",
    )
    return len(rows)


def add_session(
    session: Session,
    user: User,
    *,
    delivery_id: int,
    training_package: str,
    stream: str,
    weekday: str,
    start_time: dt.time,
    end_time: dt.time,
    classroom: str | None,
    trainer: str | None,
) -> AllocationSession:
    weekday = weekday.upper()
    stream = stream.upper()
    if weekday not in rules.allowed_weekdays(stream):
        raise AllocationEditError(f"{stream} cannot run on {weekday}.")
    if end_time <= start_time:
        raise AllocationEditError("The class must end after it starts.")
    if stream == "PRACTICAL" and classroom and rules.virtual_kind_for(classroom):
        raise AllocationEditError("A virtual value in a practical classroom column is refused — practical is never virtual.")
    virtual_kind = rules.virtual_kind_for(classroom or "") if classroom else None
    mode = "VIRTUAL" if virtual_kind or stream == "MSCRIS" else "PHYSICAL"
    row = AllocationSession(
        training_package=training_package.upper(),
        delivery_id=delivery_id,
        stream=stream,
        weekday=rules.MSCRIS_WEEKDAY if stream == "MSCRIS" else weekday,
        start_time=start_time,
        end_time=end_time,
        delivery_mode=mode,
        facility_id=None,
        virtual_kind=virtual_kind or ("FACE_TO_FACE_VC" if stream == "MSCRIS" else None),
        classroom_text=(
            rules.CANONICAL_VIRTUAL_CLASSROOM
            if virtual_kind or stream == "MSCRIS"
            else classroom
        ),
        trainer_id=None,
        trainer_text=trainer,
    )
    session.add(row)
    session.flush()
    record_activity(
        session,
        user=user,
        action="UPDATE",
        page_or_function="Page 1 - Timetable View and Management",
        detail=f"Added {stream} on {row.weekday} to delivery {delivery_id}.",
        record_reference=str(row.id),
        result="COMPLETED",
    )
    return row


def remove_session(session: Session, user: User, *, session_id: int, training_package: str) -> None:
    row = _session_row(session, session_id, training_package)
    detail = f"Removed {row.stream} on {row.weekday} (session {row.id})."
    session.delete(row)
    session.flush()
    record_activity(
        session,
        user=user,
        action="UPDATE",
        page_or_function="Page 1 - Timetable View and Management",
        detail=detail,
        record_reference=str(session_id),
        result="COMPLETED",
    )
