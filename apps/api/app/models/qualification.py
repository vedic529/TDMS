"""Qualifications, units and the approved delivery order (Schema v1 §7.4).

Qualifications are **national**, not owned by a college — RTO is the College and
is reached through `course_offerings` (DBQ-06, SRS §1.4).
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import enums
from app.db.base import Base, SoftDeleteMixin, pk_column, soft_delete_check


class Qualification(Base):
    """An approved VET qualification (Page 4A Qualification Code / Title)."""

    __tablename__ = "qualifications"
    __table_args__ = (
        # Unique where a code exists; several code-less ELICOS qualifications
        # may coexist.
        Index(
            "uq_qualifications_qualification_code",
            "qualification_code",
            unique=True,
            postgresql_where=text("qualification_code IS NOT NULL"),
        ),
    )

    id: Mapped[int] = pk_column()
    # Nullable, and unique only where present (partial index below).
    #
    # ELICOS courses have no VET Code. Storing a literal 'NA' in each would
    # collide on a UNIQUE column, and dropping uniqueness altogether would let
    # two qualifications share a real code — unacceptable, since this is the
    # business key students, trainers and timetables resolve against. NULL means
    # "not supplied"; the interface shows NA and the field stays editable.
    qualification_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualification_title: Mapped[str] = mapped_column(Text, nullable=False)

    # Nullable: the SRS does not mark these required and real VET extracts are
    # frequently incomplete.
    course_level: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_of_education_broad: Mapped[str | None] = mapped_column(Text, nullable=True)
    field_of_education_narrow: Mapped[str | None] = mapped_column(Text, nullable=True)
    course_sector: Mapped[str | None] = mapped_column(Text, nullable=True)
    # SRS §8.3 Source URL - the approved verification reference.
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    unit_links: Mapped[list[QualificationUnit]] = relationship(back_populates="qualification")
    supersessions: Mapped[list[QualificationSupersession]] = relationship(
        back_populates="qualification", cascade="all, delete-orphan", passive_deletes=False
    )


class QualificationSupersession(Base):
    """A retired qualification code and the qualification that replaced it.

    `CHC30121` was superseded by `CHC30125`; students enrolled under the old code
    belong to the current qualification. This is a business decision, so it is
    stored as data rather than buried in a constant.

    `superseded_code` is text and deliberately **not** a foreign key: a retired
    code is not a qualification, so there is no row for it to reference. That
    also makes the direction unambiguous — the text side is always the retired
    one, and the foreign key always points at the survivor.
    """

    __tablename__ = "qualification_supersessions"
    __table_args__ = (
        UniqueConstraint(
            "superseded_code", name="uq_qualification_supersessions_superseded_code"
        ),
        Index("ix_qualification_supersessions_qualification_id", "qualification_id"),
    )

    id: Mapped[int] = pk_column()
    superseded_code: Mapped[str] = mapped_column(Text, nullable=False)
    qualification_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("qualifications.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    qualification: Mapped[Qualification] = relationship(back_populates="supersessions")


class Unit(Base):
    """An approved Unit of Competency. Reusable across qualifications."""

    __tablename__ = "units"

    id: Mapped[int] = pk_column()
    unit_code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    unit_title: Mapped[str] = mapped_column(Text, nullable=False)
    uoc_type: Mapped[str | None] = mapped_column(enums.uoc_type, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    qualification_links: Mapped[list[QualificationUnit]] = relationship(back_populates="unit")


class QualificationUnit(Base, SoftDeleteMixin):
    """Which units belong to a qualification, and in what order.

    An association entity, not a bare secondary table, because the relationship
    carries business data: `delivery_order`.

    **`delivery_order` is an internal ordinal that is never displayed.** SRS §8.3
    says Page 4B shows no Sequence ID and that row order carries the sequence —
    but a SQL table has no inherent row order, so without this column TT-08
    ("schedules must follow the approved unit sequence") is unimplementable.
    Approved under DBQ-05.

    DBQ-07: one sequence per qualification, **not** per campus. Page 4's
    college/campus filter reaches units through `course_offerings`.
    """

    __tablename__ = "qualification_units"
    __table_args__ = (
        UniqueConstraint("qualification_id", "unit_id", name="uq_qualification_units_qualification_id_unit_id"),
        UniqueConstraint(
            "qualification_id",
            "delivery_order",
            name="uq_qualification_units_qualification_id_delivery_order",
            # Deferrable so a whole reorder can be applied inside one
            # transaction without tripping the constraint mid-update.
            deferrable=True,
            initially="DEFERRED",
        ),
        soft_delete_check(),
    )

    id: Mapped[int] = pk_column()
    qualification_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("qualifications.id", ondelete="RESTRICT"), nullable=False
    )
    unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("units.id", ondelete="RESTRICT"), nullable=False
    )
    #: NULL means "membership known, delivery order not yet supplied by an
    #: approved timetable source". Qualification Data gives membership; a rolling
    #: timetable gives order. Requiring both would mean inventing a sequence for
    #: every qualification whose timetable has not been approved yet.
    delivery_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    qualification: Mapped[Qualification] = relationship(back_populates="unit_links")
    unit: Mapped[Unit] = relationship(back_populates="qualification_links")
