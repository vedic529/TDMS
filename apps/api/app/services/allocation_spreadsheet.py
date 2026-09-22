"""Allocation-level rows and controlled choices for the spreadsheet view."""

from __future__ import annotations

import datetime as dt
from collections import defaultdict

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models.allocation import AllocationDelivery, AllocationDeliveryIntake, AllocationSession
from app.models.college import Campus, College
from app.models.course import CourseOffering
from app.models.facility import Facility
from app.models.qualification import Qualification, Unit
from app.models.student import Student, StudentGroup
from app.models.trainer import Trainer, TrainerAvailability, TrainerUnit
from app.services import facilities
from app.services.allocation_rules import CANONICAL_VIRTUAL_CLASSROOM


def list_rows(
    session: Session,
    *,
    training_package: str,
    start_date: dt.date,
    end_date: dt.date | None,
    limit: int,
    offset: int,
) -> dict:
    """One row per delivery. Related records are loaded in fixed-size batches."""
    package = training_package.upper()
    conditions = [
        AllocationDelivery.training_package == package,
        AllocationDelivery.end_date >= start_date,
        AllocationDelivery.is_quarantined.is_(False),
    ]
    if end_date is not None:
        conditions.append(AllocationDelivery.start_date <= end_date)
    filtered = select(AllocationDelivery).where(*conditions)
    total = session.execute(select(func.count()).select_from(filtered.subquery())).scalar_one()
    deliveries = list(
        session.execute(
            filtered.order_by(
                AllocationDelivery.start_date,
                AllocationDelivery.qualification_id,
                AllocationDelivery.unit_id,
                AllocationDelivery.id,
            ).limit(limit).offset(offset)
        ).scalars()
    )
    if not deliveries:
        return {"items": [], "total": total, "limit": limit, "offset": offset}

    ids = [row.id for row in deliveries]
    qualification_ids = {row.qualification_id for row in deliveries if row.qualification_id}
    unit_ids = {row.unit_id for row in deliveries if row.unit_id}
    college_ids = {row.college_id for row in deliveries if row.college_id}
    campus_ids = {row.campus_id for row in deliveries if row.campus_id}
    qualifications = {
        row.id: row for row in session.execute(select(Qualification).where(Qualification.id.in_(qualification_ids))).scalars()
    }
    units = {row.id: row for row in session.execute(select(Unit).where(Unit.id.in_(unit_ids))).scalars()}
    colleges = {row.id: row for row in session.execute(select(College).where(College.id.in_(college_ids))).scalars()}
    campuses = {row.id: row for row in session.execute(select(Campus).where(Campus.id.in_(campus_ids))).scalars()}

    intake_map: dict[int, list[str]] = defaultdict(list)
    for delivery_id, label in session.execute(
        select(AllocationDeliveryIntake.delivery_id, AllocationDeliveryIntake.intake_label)
        .where(
            AllocationDeliveryIntake.training_package == package,
            AllocationDeliveryIntake.delivery_id.in_(ids),
        )
        .order_by(AllocationDeliveryIntake.intake_label)
    ):
        intake_map[delivery_id].append(label)

    session_map: dict[int, list[dict]] = defaultdict(list)
    session_rows = session.execute(
        select(AllocationSession, Facility, Trainer)
        .outerjoin(Facility, Facility.id == AllocationSession.facility_id)
        .outerjoin(Trainer, Trainer.id == AllocationSession.trainer_id)
        .where(
            AllocationSession.training_package == package,
            AllocationSession.delivery_id.in_(ids),
            AllocationSession.stream.in_(("THEORY", "PRACTICAL")),
        )
        .order_by(AllocationSession.delivery_id, AllocationSession.stream, AllocationSession.weekday)
    ).all()
    for stored, room, trainer in session_rows:
        session_map[stored.delivery_id].append(
            {
                "session_id": stored.id,
                "stream": stored.stream,
                "weekday": stored.weekday,
                "start_time": stored.start_time.strftime("%H:%M"),
                "end_time": stored.end_time.strftime("%H:%M"),
                "delivery_mode": stored.delivery_mode,
                "facility_id": stored.facility_id,
                "classroom": room.facility_reference if room else (stored.classroom_text or ""),
                "classroom_capacity": room.capacity if room else None,
                "trainer": trainer.trainer_name if trainer else (stored.trainer_text or ""),
                "trainer_id": stored.trainer_id,
            }
        )

    attendance = defaultdict(lambda: {"total": 0, "coe": 0, "non_coe": 0})
    attendance_rows = session.execute(
        select(
            CourseOffering.college_id,
            CourseOffering.campus_id,
            CourseOffering.qualification_id,
            StudentGroup.rolling_intake_label,
            Student.coe_status,
            func.count(Student.id),
        )
        .join(CourseOffering, CourseOffering.id == Student.course_offering_id)
        .join(StudentGroup, StudentGroup.id == Student.student_group_id)
        .where(
            Student.is_deleted.is_(False),
            Student.status == "ACTIVE",
            StudentGroup.rolling_intake_label.isnot(None),
        )
        .group_by(
            CourseOffering.college_id,
            CourseOffering.campus_id,
            CourseOffering.qualification_id,
            StudentGroup.rolling_intake_label,
            Student.coe_status,
        )
    ).all()
    for college_id, campus_id, qualification_id, label, coe_status, count in attendance_rows:
        bucket = attendance[(college_id, campus_id, qualification_id, label)]
        bucket["total"] += count
        bucket["coe" if coe_status == "COE" else "non_coe"] += count

    items = []
    for index, delivery in enumerate(deliveries, start=offset + 1):
        intake_labels = intake_map[delivery.id]
        counts = {"total": 0, "coe": 0, "non_coe": 0}
        for label in intake_labels:
            part = attendance[(delivery.college_id, delivery.campus_id, delivery.qualification_id, label)]
            for key in counts:
                counts[key] += part[key]
        qualification = qualifications.get(delivery.qualification_id)
        unit = units.get(delivery.unit_id)
        college = colleges.get(delivery.college_id)
        campus = campuses.get(delivery.campus_id)
        items.append(
            {
                "sl_no": index,
                "delivery_id": delivery.id,
                "college": college.college_short_name if college else (delivery.college_text or ""),
                "campus": campus.campus_name if campus else (delivery.campus_text or ""),
                "qualification_code": qualification.qualification_code if qualification else (delivery.qualification_text or ""),
                "qualification_title": qualification.qualification_title if qualification else "",
                "duration_weeks": delivery.duration_weeks,
                "group": delivery.group_code,
                "intakes": intake_labels,
                "total_students": counts["total"],
                "coe_students": counts["coe"],
                "non_coe_students": counts["non_coe"],
                "unit_code": unit.unit_code if unit else (delivery.unit_text or ""),
                "unit_title": unit.unit_title if unit else "",
                "unit_start_date": delivery.start_date,
                "unit_end_date": delivery.end_date,
                "uoc_type": delivery.uoc_type,
                "mode_of_delivery": delivery.mode_of_delivery,
                "sessions": session_map[delivery.id],
            }
        )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def choices(
    session: Session,
    *,
    delivery_id: int,
    training_package: str,
    stream: str,
    weekday: str,
    start_time: dt.time,
    end_time: dt.time,
    delivery_mode: str,
) -> dict:
    package = training_package.upper()
    delivery = session.execute(
        select(AllocationDelivery).where(
            AllocationDelivery.id == delivery_id,
            AllocationDelivery.training_package == package,
            AllocationDelivery.is_quarantined.is_(False),
        )
    ).scalar_one_or_none()
    if delivery is None:
        raise ValueError("That allocation row was not found.")
    qualification = session.get(Qualification, delivery.qualification_id)

    room_items = []
    allow_virtual = stream == "THEORY" and delivery.mode_of_delivery in {"F2FPV", "F2FV"}
    allow_physical = stream == "PRACTICAL" or delivery.mode_of_delivery in {"F2FP", "F2FPV"}
    if allow_virtual:
        room_items.append({"name": CANONICAL_VIRTUAL_CLASSROOM, "capacity": None})
    if allow_physical and qualification is not None:
        for item in facilities.eligible_facilities(
            session,
            qualification_code=qualification.qualification_code,
            weekday=weekday,
            campus_id=delivery.campus_id,
            college_id=delivery.college_id,
        ):
            room_items.append({"id": item.facility.id, "name": item.facility.facility_reference, "capacity": item.facility.capacity})

    weekday_column = getattr(TrainerAvailability, weekday.lower())
    class_types = (stream, "THEORY_AND_PRACTICAL")
    trainer_rows = session.execute(
        select(Trainer.id, Trainer.trainer_name)
        .join(TrainerUnit, TrainerUnit.trainer_id == Trainer.id)
        .join(TrainerAvailability, TrainerAvailability.trainer_id == Trainer.id)
        .where(
            Trainer.is_deleted.is_(False),
            Trainer.is_active.is_(True),
            TrainerUnit.qualification_id == delivery.qualification_id,
            TrainerUnit.unit_id == delivery.unit_id,
            TrainerAvailability.campus_id == delivery.campus_id,
            TrainerAvailability.class_type.in_(class_types),
            weekday_column == delivery_mode,
            TrainerAvailability.working_time_start <= start_time,
            TrainerAvailability.working_time_end >= end_time,
        )
        .distinct()
        .order_by(Trainer.trainer_name)
    ).all()
    return {
        "classrooms": room_items,
        "trainers": [{"id": trainer_id, "name": name} for trainer_id, name in trainer_rows],
    }
