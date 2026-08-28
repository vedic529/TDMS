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
from sqlalchemy import text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import enums
from app.db.base import Base, SoftDeleteMixin, pk_column, soft_delete_check


class Trainer(Base, SoftDeleteMixin):
    """An approved trainer.

    `Serial Number` (SRS §7.3) is **not** stored — it is a display sequence
    produced by `ROW_NUMBER()` in the query, not data.
    """

    __tablename__ = "trainers"
    __table_args__ = (soft_delete_check(), Index("ix_trainers_city", "city"))

    id: Mapped[int] = pk_column()
    trainer_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    trainer_name: Mapped[str] = mapped_column(Text, nullable=False)
    #: The source file's `Trainer Campus` — a city, not a campus. Required when
    #: a trainer is added by hand; nullable because the imported records predate
    #: it and a guess would be indistinguishable from data.
    city: Mapped[str | None] = mapped_column(Text, nullable=True)
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
        # Two partial uniques rather than one constraint, because `campus_id` is
        # nullable and PostgreSQL treats NULLs as distinct — a single constraint
        # would accept two identical offshore rows for the same trainer.
        Index(
            "uq_trainer_availability_campus",
            "trainer_id",
            "campus_id",
            "class_type",
            "working_time_start",
            unique=True,
            postgresql_where=text("campus_id IS NOT NULL"),
        ),
        Index(
            "uq_trainer_availability_no_campus",
            text("trainer_id"),
            text("upper(btrim(location_text))"),
            text("class_type"),
            text("working_time_start"),
            unique=True,
            postgresql_where=text("campus_id IS NULL"),
        ),
        CheckConstraint("working_time_end > working_time_start", name="working_time_ordered"),
        # Offshore and "at a campus" are different states, not overlapping ones.
        CheckConstraint(
            "is_offshore = false OR campus_id IS NULL", name="offshore_has_no_campus"
        ),
        Index("ix_trainer_availability_campus_id", "campus_id"),
    )

    id: Mapped[int] = pk_column()
    trainer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trainers.id", ondelete="CASCADE"), nullable=False
    )
    # Nullable since 27 August 2026: one row of the real source file reads
    # Offshore, and that trainer is not at a campus at all.
    campus_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("campuses.id", ondelete="RESTRICT"), nullable=True
    )
    location: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: The raw `Location` value, set **only** when `campus_id` could not be
    #: resolved — the same pattern `allocation_delivery.campus_text` uses. It is
    #: what a resolved suggestion matches on to repair the row. `location` above
    #: stays the free-text site descriptor it has always been.
    location_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: True when the trainer works offshore. An offshore row is not a campus row
    #: with a missing campus, and must be distinguishable from a campus that
    #: merely failed to resolve.
    is_offshore: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    location_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Renamed from "Delivery Type" by the current SRS §7.3 (conflict C-5).
    class_type: Mapped[str] = mapped_column(enums.class_type, nullable=False)
    # Replaces the free-text "09:00 - 17:00" so a window can be compared with a
    # session time.
    working_time_start: Mapped[dt.time] = mapped_column(Time, nullable=False)
    working_time_end: Mapped[dt.time] = mapped_column(Time, nullable=False)
    #: The window exactly as the file wrote it. The parsed times cannot hold the
    #: `AEST/AEDT` suffix, and dropping it would lose the timezone from a record
    #: that spans three of them.
    working_time_text: Mapped[str | None] = mapped_column(Text, nullable=True)

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
        # Scoped by qualification since 27 August 2026: the same unit is
        # legitimately taught under two qualifications, and the real file holds
        # 98 such pairs. The old `UNIQUE (trainer_id, unit_id)` collapsed them.
        #
        # An expression index rather than a constraint, because either half may
        # be an unmatched value held as text. A plain unique would stop
        # deduplicating the moment `unit_id` is nullable — PostgreSQL treats
        # NULLs as distinct — so one unmatched unit could be stored against a
        # trainer many times.
        Index(
            "uq_trainer_units_link",
            text("trainer_id"),
            text(
                "coalesce(qualification_id::text, "
                "'t:' || upper(btrim(regexp_replace(qualification_text, '\s+', ' ', 'g'))))"
            ),
            text(
                "coalesce(unit_id::text, "
                "'t:' || upper(btrim(regexp_replace(unit_text, '\s+', ' ', 'g'))))"
            ),
            unique=True,
        ),
        Index(
            "ix_trainer_units_unit_text_norm",
            text("upper(btrim(regexp_replace(unit_text, '\s+', ' ', 'g')))"),
            postgresql_where=text("unit_text IS NOT NULL"),
        ),
        Index(
            "ix_trainer_units_qualification_text_norm",
            text("upper(btrim(regexp_replace(qualification_text, '\s+', ' ', 'g')))"),
            postgresql_where=text("qualification_text IS NOT NULL"),
        ),
        # A row always says what it means: an approved id, or the raw value.
        CheckConstraint(
            "unit_id IS NOT NULL OR unit_text IS NOT NULL", name="unit_resolved_or_recorded"
        ),
        CheckConstraint(
            "qualification_id IS NOT NULL OR qualification_text IS NOT NULL",
            name="qualification_resolved_or_recorded",
        ),
        Index("ix_trainer_units_unit_id", "unit_id"),
        Index("ix_trainer_units_qualification_id", "qualification_id"),
    )

    id: Mapped[int] = pk_column()
    trainer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("trainers.id", ondelete="CASCADE"), nullable=False
    )
    #: Nullable only because the table already held rows written before the
    #: qualification was recorded. Every row the importer writes sets it.
    qualification_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("qualifications.id", ondelete="RESTRICT"), nullable=True
    )
    #: Nullable since 27 August 2026, so raising a suggestion lets the row
    #: import the way the allocation import already does.
    unit_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("units.id", ondelete="RESTRICT"), nullable=True
    )
    #: The raw values, set only when the matching id could not be resolved —
    #: the same pattern `allocation_delivery` uses. They are what a resolved
    #: suggestion matches on to repair the row.
    unit_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualification_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    trainer: Mapped[Trainer] = relationship(back_populates="unit_links")
