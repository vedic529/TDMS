"""Timetable plan, unit delivery and session (Schema v1 §13).

DBQ-12 approved the **three-level normalised model** over one wide table:

    timetable_plans            one per student group - the course timetable
      └─ timetable_unit_deliveries   one per unit scheduled for that group
           └─ timetable_sessions     one per weekly slot

The plan level exists because TT-08 (approved duration and unit sequence) and
TT-10 (a course must not finish on a break) are statements about a whole course
for a group, not about a single unit.

TT-06 clash detection becomes ONE self-join over `timetable_sessions` — same
weekday, overlapping times, overlapping parent date ranges, and the same
trainer / facility / group.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import enums
from app.db.base import Base, SoftDeleteMixin, TimestampMixin, pk_column, soft_delete_check


class TimetablePlan(Base, SoftDeleteMixin, TimestampMixin):
    """The course timetable for one student group."""

    __tablename__ = "timetable_plans"
    __table_args__ = (soft_delete_check(),)

    id: Mapped[int] = pk_column()
    # Displayed timetable record number, used in confirmations and activity
    # records (TT-14).
    plan_reference: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    student_group_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("student_groups.id", ondelete="RESTRICT"), nullable=False
    )
    course_offering_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("course_offerings.id", ondelete="RESTRICT"), nullable=False
    )
    duration_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    # Only when the class size differs from the group's expected size
    # (SRS §5.3 Classroom Size).
    class_size_override: Mapped[int | None] = mapped_column(Integer, nullable=True)

    unit_deliveries: Mapped[list[TimetableUnitDelivery]] = relationship(
        back_populates="timetable_plan", cascade="all, delete-orphan", passive_deletes=True
    )


class TimetableUnitDelivery(Base, SoftDeleteMixin):
    """One unit scheduled for one group, with its date range and delivery mode."""

    __tablename__ = "timetable_unit_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "timetable_plan_id", "unit_id", name="uq_timetable_unit_deliveries_timetable_plan_id_unit_id"
        ),
        CheckConstraint("end_date >= start_date", name="delivery_dates_ordered"),
        # TT-03: the date-range overlap filter is the most frequent query on
        # Page 1.
        Index("ix_timetable_unit_deliveries_start_date_end_date", "start_date", "end_date"),
        soft_delete_check(),
    )

    id: Mapped[int] = pk_column()
    timetable_plan_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("timetable_plans.id", ondelete="CASCADE"), nullable=False
    )
    unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("units.id", ondelete="RESTRICT"), nullable=False
    )
    mode_of_delivery: Mapped[str] = mapped_column(enums.mode_of_delivery, nullable=False)
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    # `uoc_type` is deliberately NOT duplicated here - it lives on `units`.

    timetable_plan: Mapped[TimetablePlan] = relationship(back_populates="unit_deliveries")
    sessions: Mapped[list[TimetableSession]] = relationship(
        back_populates="unit_delivery", cascade="all, delete-orphan", passive_deletes=True
    )


class TimetableSession(Base, SoftDeleteMixin):
    """One weekly delivery slot.

    A single table replaces the frontend's `theory_*` / `practical_*` /
    `mscris_*` triplication. MSCRIS additional classes are represented as
    `session_type = 'ADDITIONAL'` (DBQ-14) rather than by a separate table.

    Date storage is a **weekly pattern**, not materialised occurrences: the slot
    carries weekday and times, and the parent unit delivery carries the date
    range. Classroom capacity is not stored — it is read from
    `facilities.capacity` (DATA-02).
    """

    __tablename__ = "timetable_sessions"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="session_times_ordered"),
        # DBQ-14: MSCRIS is virtual only.
        CheckConstraint(
            "session_type <> 'ADDITIONAL' OR delivery_mode = 'VIRTUAL'",
            name="additional_sessions_are_virtual",
        ),
        # DBQ-14: the free-text trainer exception is confined to additional
        # classes, so THEORY and PRACTICAL cannot bypass approved trainer data
        # (DATA-02).
        CheckConstraint(
            "session_type = 'ADDITIONAL' OR trainer_name_text IS NULL",
            name="free_text_trainer_only_for_additional",
        ),
        # TT-06 clash detection.
        Index(
            "ix_timetable_sessions_trainer_id_weekday",
            "trainer_id",
            "weekday",
            postgresql_where=text("trainer_id IS NOT NULL"),
        ),
        Index(
            "ix_timetable_sessions_facility_id_weekday",
            "facility_id",
            "weekday",
            postgresql_where=text("facility_id IS NOT NULL"),
        ),
        Index("ix_timetable_sessions_timetable_unit_delivery_id", "timetable_unit_delivery_id"),
        soft_delete_check(),
    )

    id: Mapped[int] = pk_column()
    timetable_unit_delivery_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("timetable_unit_deliveries.id", ondelete="CASCADE"), nullable=False
    )
    session_type: Mapped[str] = mapped_column(enums.session_type, nullable=False)
    # The topic an additional class covers (DBQ-14).
    session_title: Mapped[str | None] = mapped_column(Text, nullable=True)

    weekday: Mapped[str] = mapped_column(enums.weekday, nullable=False)
    start_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[dt.time] = mapped_column(Time, nullable=False)

    # TRN-04 / DATA-03: RESTRICT, so an inactive trainer or facility remains
    # resolvable in historical records.
    trainer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("trainers.id", ondelete="RESTRICT"), nullable=True
    )
    # Free-text trainer, ADDITIONAL sessions only (DBQ-14).
    trainer_name_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Null for a virtual session.
    facility_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("facilities.id", ondelete="RESTRICT"), nullable=True
    )
    delivery_mode: Mapped[str] = mapped_column(enums.mode_of_delivery, nullable=False)

    unit_delivery: Mapped[TimetableUnitDelivery] = relationship(back_populates="sessions")


class TimetableClashOverride(Base):
    """An approved clash override (TT-06).

    Recorded as data rather than a free-text note, so "which clashes were
    overridden and by whom" is answerable. Who may approve one is OD-06.
    """

    __tablename__ = "timetable_clash_overrides"

    id: Mapped[int] = pk_column()
    timetable_session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("timetable_sessions.id", ondelete="CASCADE"), nullable=False
    )
    conflicting_session_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("timetable_sessions.id", ondelete="RESTRICT"), nullable=True
    )
    reason_code_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reason_codes.id", ondelete="RESTRICT"), nullable=False
    )
    reason_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_by_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    approved_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
