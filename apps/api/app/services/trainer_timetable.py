"""A trainer's monthly teaching calendar, derived from allocation records."""

from __future__ import annotations

import datetime as dt
from calendar import monthrange
from collections import defaultdict

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.models.allocation import AllocationDelivery, AllocationDeliveryIntake, AllocationSession
from app.models.college import Campus, College
from app.models.course import CourseOffering
from app.models.facility import Facility
from app.models.qualification import Unit
from app.models.student import Student, StudentGroup
from app.models.trainer import Trainer
from app.services.trainers import TrainerError

WEEKDAYS = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")


def _trainer(session: Session, trainer_id: int) -> Trainer:
    trainer = session.scalar(
        select(Trainer).where(Trainer.id == trainer_id, Trainer.is_deleted.is_(False))
    )
    if trainer is None:
        raise TrainerError("Trainer not found.")
    return trainer


def _room(row) -> str:
    if row.facility_reference:
        return row.facility_reference
    if row.classroom_text:
        return row.classroom_text
    if row.delivery_mode == "VIRTUAL":
        return "Face to Face VC"
    return "Classroom not recorded"


def _room_key(row) -> str:
    if row.facility_id is not None:
        return f"facility:{row.facility_id}"
    return "text:" + " ".join(_room(row).upper().split())


def calendar_month(session: Session, trainer_id: int, month: dt.date) -> dict:
    trainer = _trainer(session, trainer_id)
    first = month.replace(day=1)
    last = month.replace(day=monthrange(month.year, month.month)[1])

    rows = session.execute(
        select(
            AllocationSession.id,
            AllocationSession.training_package,
            AllocationSession.weekday,
            AllocationSession.start_time,
            AllocationSession.end_time,
            AllocationSession.stream,
            AllocationSession.delivery_mode,
            AllocationSession.facility_id,
            AllocationSession.classroom_text,
            AllocationDelivery.id.label("delivery_id"),
            AllocationDelivery.start_date,
            AllocationDelivery.end_date,
            AllocationDelivery.uoc_type,
            AllocationDelivery.unit_text,
            AllocationDelivery.college_text,
            AllocationDelivery.campus_text,
            Unit.id.label("unit_id"),
            Unit.unit_code,
            Unit.unit_title,
            College.college_short_name,
            Campus.campus_name,
            Facility.facility_reference,
        )
        .join(
            AllocationDelivery,
            and_(
                AllocationDelivery.id == AllocationSession.delivery_id,
                AllocationDelivery.training_package == AllocationSession.training_package,
            ),
        )
        .outerjoin(Unit, Unit.id == AllocationDelivery.unit_id)
        .outerjoin(College, College.id == AllocationDelivery.college_id)
        .outerjoin(Campus, Campus.id == AllocationDelivery.campus_id)
        .outerjoin(Facility, Facility.id == AllocationSession.facility_id)
        .where(
            AllocationSession.trainer_id == trainer_id,
            AllocationDelivery.is_quarantined.is_(False),
            AllocationDelivery.start_date <= last,
            AllocationDelivery.end_date >= first,
        )
        .order_by(AllocationSession.start_time, AllocationSession.id)
    ).all()

    # Co-trainers share a delivery *and* a stream. A trainer handling a
    # practical session is therefore never presented as a co-trainer for the
    # theory sessions of that unit, and vice versa.
    delivery_streams = {
        (row.training_package, row.delivery_id, row.stream)
        for row in rows
        if row.stream in {"THEORY", "PRACTICAL"}
    }
    co_trainers_by_delivery_stream: dict[tuple[str, int, str], set[tuple[int, str]]] = defaultdict(set)
    if delivery_streams:
        delivery_ids = {delivery_id for _, delivery_id, _ in delivery_streams}
        training_packages = {training_package for training_package, _, _ in delivery_streams}
        co_trainer_rows = session.execute(
            select(
                AllocationSession.training_package,
                AllocationSession.delivery_id,
                AllocationSession.stream,
                AllocationSession.trainer_id,
                Trainer.trainer_name,
            )
            .join(Trainer, Trainer.id == AllocationSession.trainer_id)
            .where(
                AllocationSession.delivery_id.in_(delivery_ids),
                AllocationSession.training_package.in_(training_packages),
                AllocationSession.stream.in_(("THEORY", "PRACTICAL")),
                AllocationSession.trainer_id.is_not(None),
            )
        ).all()
        for co_trainer_row in co_trainer_rows:
            key = (
                co_trainer_row.training_package,
                co_trainer_row.delivery_id,
                co_trainer_row.stream,
            )
            if key in delivery_streams:
                co_trainers_by_delivery_stream[key].add(
                    (co_trainer_row.trainer_id, co_trainer_row.trainer_name)
                )

    by_day: dict[dt.date, dict[tuple[str, str], dict]] = defaultdict(dict)
    for row in rows:
        cursor = max(first, row.start_date)
        end = min(last, row.end_date)
        while cursor <= end:
            if WEEKDAYS[cursor.weekday()] == row.weekday:
                unit_code = row.unit_code or row.unit_text or "Unit not recorded"
                unit_title = row.unit_title or "Unit title not recorded"
                room = _room(row)
                room_key = _room_key(row)
                key = (unit_code.upper(), room_key)
                item = by_day[cursor].setdefault(
                    key,
                    {
                        "class_key": f"{cursor.isoformat()}|{unit_code}|{room_key}",
                        "session_ids": set(),
                        "unit_code": unit_code,
                        "unit_title": unit_title,
                        "classroom": room,
                        "colleges": set(),
                        "campuses": set(),
                        "times": set(),
                        "delivery_modes": set(),
                        "uoc_types": set(),
                        "streams": set(),
                        "co_trainers": set(),
                        # There is no Moodle URL column in the current schema.
                        "moodle_link": None,
                    },
                )
                item["session_ids"].add(row.id)
                item["colleges"].add(row.college_short_name or row.college_text or "College not recorded")
                item["campuses"].add(row.campus_name or row.campus_text or "Campus not recorded")
                item["times"].add(f"{row.start_time.strftime('%H:%M')}–{row.end_time.strftime('%H:%M')}")
                item["delivery_modes"].add(row.delivery_mode.title())
                item["uoc_types"].add(row.uoc_type.title())
                item["streams"].add(row.stream.title())
                if row.stream in {"THEORY", "PRACTICAL"}:
                    item["co_trainers"].update(
                        name
                        for other_trainer_id, name in co_trainers_by_delivery_stream[
                            (row.training_package, row.delivery_id, row.stream)
                        ]
                        if other_trainer_id != trainer.id
                    )
            cursor += dt.timedelta(days=1)

    days = []
    cursor = first
    while cursor <= last:
        classes = []
        for item in by_day.get(cursor, {}).values():
            classes.append(
                {
                    **item,
                    "session_ids": sorted(item["session_ids"]),
                    "colleges": sorted(item["colleges"]),
                    "campuses": sorted(item["campuses"]),
                    "times": sorted(item["times"]),
                    "delivery_modes": sorted(item["delivery_modes"]),
                    "uoc_types": sorted(item["uoc_types"]),
                    "streams": sorted(item["streams"]),
                    "co_trainers": sorted(item["co_trainers"]),
                }
            )
        classes.sort(key=lambda item: (item["times"], item["unit_code"], item["classroom"]))
        days.append({"date": cursor, "classes": classes})
        cursor += dt.timedelta(days=1)

    return {
        "trainer_id": trainer.id,
        "trainer_name": trainer.trainer_name,
        "month": first.strftime("%Y-%m"),
        "days": days,
    }


def attending_students(
    session: Session, trainer_id: int, class_date: dt.date, session_ids: list[int]
) -> dict:
    _trainer(session, trainer_id)
    if not session_ids:
        return {"items": [], "total": 0}

    rows = session.execute(
        select(
            AllocationDelivery.college_id,
            AllocationDelivery.campus_id,
            AllocationDelivery.qualification_id,
            AllocationDeliveryIntake.intake_label,
        )
        .select_from(AllocationSession)
        .join(
            AllocationDelivery,
            and_(
                AllocationDelivery.id == AllocationSession.delivery_id,
                AllocationDelivery.training_package == AllocationSession.training_package,
            ),
        )
        .join(
            AllocationDeliveryIntake,
            and_(
                AllocationDeliveryIntake.delivery_id == AllocationDelivery.id,
                AllocationDeliveryIntake.training_package == AllocationDelivery.training_package,
            ),
        )
        .where(
            AllocationSession.id.in_(session_ids),
            AllocationSession.trainer_id == trainer_id,
            AllocationSession.weekday == WEEKDAYS[class_date.weekday()],
            AllocationDelivery.start_date <= class_date,
            AllocationDelivery.end_date >= class_date,
            AllocationDelivery.is_quarantined.is_(False),
        )
    ).all()

    scopes = {
        (row.college_id, row.campus_id, row.qualification_id, row.intake_label)
        for row in rows
        if row.college_id and row.campus_id and row.qualification_id and row.intake_label
    }
    if not scopes:
        return {"items": [], "total": 0}

    conditions = [
        and_(
            CourseOffering.college_id == college_id,
            CourseOffering.campus_id == campus_id,
            CourseOffering.qualification_id == qualification_id,
            StudentGroup.rolling_intake_label == intake_label,
        )
        for college_id, campus_id, qualification_id, intake_label in scopes
    ]
    students = session.execute(
        select(Student)
        .join(CourseOffering, CourseOffering.id == Student.course_offering_id)
        .join(StudentGroup, StudentGroup.id == Student.student_group_id)
        .where(Student.is_deleted.is_(False), Student.status == "ACTIVE", or_(*conditions))
        .distinct()
        .order_by(Student.first_name, Student.last_name, Student.student_id)
    ).scalars().all()
    items = [
        {
            "id": student.id,
            "student_id": student.student_id,
            "first_name": student.first_name,
            "last_name": student.last_name,
            "coe_status": student.coe_status,
        }
        for student in students
    ]
    return {"items": items, "total": len(items)}
