"""Calendar month view. Cost: exactly two queries."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Select, and_, func, select
from sqlalchemy.orm import Session

from app.models.allocation import AllocationDelivery, AllocationDeliveryIntake, AllocationSession
from app.models.college import Campus, College
from app.models.facility import Facility
from app.models.qualification import Qualification, Unit
from app.models.timetable import RollingTimetableWeek
from app.models.trainer import Trainer

CALENDAR_QUERY_COUNT = 2

WEEKDAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")


def _weekday_name(day: dt.date) -> str:
    return WEEKDAYS[day.weekday()]


def calendar_month(
    session: Session,
    *,
    training_package: str,
    start_date: dt.date,
    end_date: dt.date,
) -> dict:
    """One query for sessions, one for rolling-timetable expectation. Never per day."""
    package = training_package.upper()
    session_stmt: Select = (
        select(
            AllocationSession.id,
            AllocationSession.training_package,
            AllocationSession.delivery_id,
            AllocationSession.stream,
            AllocationSession.weekday,
            AllocationSession.start_time,
            AllocationSession.end_time,
            AllocationSession.delivery_mode,
            AllocationSession.facility_id,
            AllocationSession.virtual_kind,
            AllocationSession.classroom_text,
            AllocationSession.trainer_id,
            AllocationSession.trainer_text,
            AllocationDelivery.start_date,
            AllocationDelivery.end_date,
            AllocationDelivery.intake_match_status,
            AllocationDelivery.classroom_size,
            Qualification.qualification_code,
            Qualification.qualification_title,
            Unit.unit_code,
            Unit.unit_title,
            College.college_short_name,
            Campus.campus_name,
            Facility.facility_reference,
            Trainer.trainer_name,
            func.coalesce(
                func.array_agg(AllocationDeliveryIntake.intake_label).filter(
                    AllocationDeliveryIntake.intake_label.isnot(None)
                ),
                [],
            ).label("intake_labels"),
        )
        .join(
            AllocationDelivery,
            and_(
                AllocationDelivery.id == AllocationSession.delivery_id,
                AllocationDelivery.training_package == AllocationSession.training_package,
            ),
        )
        .join(Qualification, Qualification.id == AllocationDelivery.qualification_id)
        .join(Unit, Unit.id == AllocationDelivery.unit_id)
        .join(College, College.id == AllocationDelivery.college_id)
        .join(Campus, Campus.id == AllocationDelivery.campus_id)
        .outerjoin(Facility, Facility.id == AllocationSession.facility_id)
        .outerjoin(Trainer, Trainer.id == AllocationSession.trainer_id)
        .outerjoin(
            AllocationDeliveryIntake,
            and_(
                AllocationDeliveryIntake.delivery_id == AllocationDelivery.id,
                AllocationDeliveryIntake.training_package == AllocationDelivery.training_package,
            ),
        )
        .where(
            AllocationSession.training_package == package,
            AllocationDelivery.start_date <= end_date,
            AllocationDelivery.end_date >= start_date,
            # A quarantined delivery is retained for audit but never operational.
            AllocationDelivery.is_quarantined.is_(False),
        )
        .group_by(
            AllocationSession.id,
            AllocationSession.training_package,
            AllocationSession.delivery_id,
            AllocationSession.stream,
            AllocationSession.weekday,
            AllocationSession.start_time,
            AllocationSession.end_time,
            AllocationSession.delivery_mode,
            AllocationSession.facility_id,
            AllocationSession.virtual_kind,
            AllocationSession.classroom_text,
            AllocationSession.trainer_id,
            AllocationSession.trainer_text,
            AllocationDelivery.start_date,
            AllocationDelivery.end_date,
            AllocationDelivery.intake_match_status,
            AllocationDelivery.classroom_size,
            Qualification.qualification_code,
            Qualification.qualification_title,
            Unit.unit_code,
            Unit.unit_title,
            College.college_short_name,
            Campus.campus_name,
            Facility.facility_reference,
            Trainer.trainer_name,
        )
    )
    session_rows = session.execute(session_stmt).all()

    rolling_stmt = (
        select(
            RollingTimetableWeek.week_start_date,
            RollingTimetableWeek.week_end_date,
            RollingTimetableWeek.intake_label,
            RollingTimetableWeek.unit_code,
            RollingTimetableWeek.schedule_type,
        ).where(
            RollingTimetableWeek.training_package == package,
            RollingTimetableWeek.week_start_date <= end_date,
            RollingTimetableWeek.week_end_date >= start_date,
            RollingTimetableWeek.schedule_type == "UNIT",
        )
    )
    rolling_rows = session.execute(rolling_stmt).all()

    days = []
    cursor = start_date
    while cursor <= end_date:
        weekday = _weekday_name(cursor)
        items = []
        for row in session_rows:
            if row.weekday != weekday:
                continue
            if cursor < row.start_date or cursor > row.end_date:
                continue
            room = row.facility_reference or row.classroom_text or ""
            trainer = row.trainer_name or row.trainer_text or ""
            # `and`/`or` return the last operand, not a boolean, so without
            # bool() this yields None or the trainer's name and Pydantic rejects
            # it — a 500 on exactly the sessions the flag exists to highlight.
            needs_allocation = bool(
                (row.delivery_mode == "PHYSICAL" and row.facility_id is None)
                or (row.stream != "MSCRIS" and row.trainer_id is None and row.trainer_text)
            )
            items.append(
                {
                    "session_id": row.id,
                    "delivery_id": row.delivery_id,
                    "stream": row.stream,
                    "weekday": row.weekday,
                    "start_time": row.start_time.strftime("%H:%M"),
                    "end_time": row.end_time.strftime("%H:%M"),
                    "unit_code": row.unit_code,
                    "unit_title": row.unit_title,
                    "qualification_code": row.qualification_code,
                    "classroom": room,
                    "trainer": trainer,
                    "delivery_mode": row.delivery_mode,
                    "virtual_kind": row.virtual_kind,
                    "intakes": sorted({label for label in (row.intake_labels or []) if label}),
                    "intake_match_status": row.intake_match_status,
                    "needs_allocation": needs_allocation,
                    "not_found": row.intake_match_status == "NOT_FOUND",
                }
            )
        expected = []
        allocated_units = {(item["unit_code"], intake) for item in items for intake in item["intakes"]}
        seen = set()
        for row in rolling_rows:
            if row.week_start_date <= cursor <= row.week_end_date and row.unit_code:
                key = (row.unit_code, row.intake_label)
                if key in seen:
                    continue
                seen.add(key)
                expected.append(
                    {
                        "unit_code": row.unit_code,
                        "intake_label": row.intake_label,
                        "scheduled": key in allocated_units or any(item["unit_code"] == row.unit_code for item in items),
                    }
                )
        days.append(
            {
                "date": cursor.isoformat(),
                "weekday": weekday,
                "sessions": items,
                "expected_units": expected,
                "student_count": 0,
            }
        )
        cursor += dt.timedelta(days=1)
    return {
        "training_package": package,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "days": days,
        "query_cost": CALENDAR_QUERY_COUNT,
        "empty": not session_rows,
    }
