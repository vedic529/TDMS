"""Trainers, availability and approved teaching scope (Schema v1 §11)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import enums
from app.db.base import Base, SoftDeleteMixin, pk_column, soft_delete_check


class Trainer(Base, SoftDeleteMixin):
    """An approved trainer.

    `Serial Number` (SRS §7.3) is **not** stored — it is a display sequence
    produced by `ROW_NUMBER()` in the query, not data.
    """

    __tablename__ = "trainers"
    __table_args__ = (soft_delete_check(),)

    id: Mapped[int] = pk_column()
    trainer_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    trainer_name: Mapped[str] = mapped_column(Text, nullable=False)
    # TRN-04: an inactive trainer stays visible for historical records but must
    # not be selectable for a new timetable assignment.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    availability: Mapped[list[TrainerAvailability]] = relationship(
        back_populates="trainer", cascade="all, delete-orphan", passive_deletes=True
    )
    qualification_links: Mapped[list[TrainerQualification]] = relationship(
        back_populates="trainer", cascade="all, delete-orphan", passive_deletes=True
    )
    unit_links: Mapped[list[TrainerUnit]] = relationship(
        back_populates="trainer", cascade="all, delete-orphan", passive_deletes=True
    )


class TrainerAvailability(Base):
    """One availability block for a trainer at a campus.

    DBQ-11 approved **five weekday columns**, matching the source spreadsheet and
    the Page 3 grid one-to-one. Because the weekday is a column rather than a
    value, clash and availability queries read the `trainer_availability_days`
    view instead, which unpivots these five columns into rows.
    """

    __tablename__ = "trainer_availability"
    __table_args__ = (
        UniqueConstraint(
            "trainer_id",
            "campus_id",
            "class_type",
            "working_time_start",
            name="uq_trainer_availability_trainer_id_campus_id_class_type_start",
        ),
        CheckConstraint("working_time_end > working_time_start", name="working_time_ordered"),
        Index("ix_trainer_availability_campus_id", "campus_id"),
    )

    id: Mapped[int] = pk_column()
    trainer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trainers.id", ondelete="CASCADE"), nullable=False
    )
    campus_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("campuses.id", ondelete="RESTRICT"), nullable=False
    )
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    location_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Renamed from "Delivery Type" by the current SRS §7.3 (conflict C-5).
    class_type: Mapped[str] = mapped_column(enums.class_type, nullable=False)
    # Replaces the free-text "09:00 - 17:00" so a window can be compared with a
    # session time.
    working_time_start: Mapped[dt.time] = mapped_column(Time, nullable=False)
    working_time_end: Mapped[dt.time] = mapped_column(Time, nullable=False)

    monday: Mapped[str] = mapped_column(enums.weekday_mode, nullable=False)
    tuesday: Mapped[str] = mapped_column(enums.weekday_mode, nullable=False)
    wednesday: Mapped[str] = mapped_column(enums.weekday_mode, nullable=False)
    thursday: Mapped[str] = mapped_column(enums.weekday_mode, nullable=False)
    friday: Mapped[str] = mapped_column(enums.weekday_mode, nullable=False)

    trainer: Mapped[Trainer] = relationship(back_populates="availability")


class TrainerQualification(Base):
    """A qualification a trainer is approved to teach (SRS §7.4).

    A junction table, not a comma-separated list: TRN-01 filters by
    qualification, which must be an indexed join rather than a `LIKE` scan.
    """

    __tablename__ = "trainer_qualifications"
    __table_args__ = (
        UniqueConstraint(
            "trainer_id", "qualification_id", name="uq_trainer_qualifications_trainer_id_qualification_id"
        ),
        # TRN-01: the reverse direction of the unique constraint.
        Index("ix_trainer_qualifications_qualification_id", "qualification_id"),
    )

    id: Mapped[int] = pk_column()
    trainer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trainers.id", ondelete="CASCADE"), nullable=False
    )
    qualification_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("qualifications.id", ondelete="RESTRICT"), nullable=False
    )

    trainer: Mapped[Trainer] = relationship(back_populates="qualification_links")


class TrainerUnit(Base):
    """A Unit of Competency a trainer is approved to deliver (SRS §7.4)."""

    __tablename__ = "trainer_units"
    __table_args__ = (
        UniqueConstraint("trainer_id", "unit_id", name="uq_trainer_units_trainer_id_unit_id"),
        Index("ix_trainer_units_unit_id", "unit_id"),
    )

    id: Mapped[int] = pk_column()
    trainer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trainers.id", ondelete="CASCADE"), nullable=False
    )
    unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("units.id", ondelete="RESTRICT"), nullable=False
    )

    trainer: Mapped[Trainer] = relationship(back_populates="unit_links")
