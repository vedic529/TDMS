"""Colleges, campuses and their approved combinations (Schema v1 §7.1).

DBQ-04 approved a **many-to-many** relationship: one physical campus can be
operated by more than one college. A 1:N model would have forced a shared site
to be entered once per college, producing duplicate campuses, duplicate
facilities, and a facility clash check unable to see two colleges booking the
same room.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, pk_column


class College(Base):
    """An approved college. Also the Page 4 **RTO** value (SRS §1.4, §8.2)."""

    __tablename__ = "colleges"

    id: Mapped[int] = pk_column()
    college_short_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    college_full_name: Mapped[str] = mapped_column(Text, nullable=False)
    # Used ONLY to build a proposed student College Email (SRS §6.1.3).
    # It is not, and must never become, an access rule (proposal §5.3).
    email_domain: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    campus_links: Mapped[list[CollegeCampus]] = relationship(back_populates="college")


class Campus(Base):
    """A physical delivery site.

    No `college_id`: a campus is shared, and the college relationship lives in
    :class:`CollegeCampus` (DBQ-04).
    """

    __tablename__ = "campuses"

    id: Mapped[int] = pk_column()
    # DBQ-15: a stable code is the identity, so a rename or rebrand does not
    # break bulk-import mapping. `campus_name` is free to change.
    campus_code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    campus_name: Mapped[str] = mapped_column(Text, nullable=False)
    campus_location: Mapped[str] = mapped_column(Text, nullable=False)
    # SRS §6.1.3: the source of the student's State.
    state: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    college_links: Mapped[list[CollegeCampus]] = relationship(back_populates="campus")
    source_addresses: Mapped[list[CampusSourceAddress]] = relationship(
        back_populates="campus", cascade="all, delete-orphan", passive_deletes=True
    )


class CampusSourceAddress(Base):
    """A spelling of a campus's address as it appears in a source system.

    One site is written several ways across the sources — Haymarket as both
    `841 George St` and `Level 2, 8 Quay St`, Melbourne three ways. The campus
    keeps one approved address; every spelling that refers to it lives here so
    incoming student and course data resolves whichever form it arrives in.

    Splitting the site into a campus per spelling would be the wrong fix: a
    campus is a place, and facility and clash checks depend on that.
    """

    __tablename__ = "campus_source_addresses"
    __table_args__ = (
        # Globally unique: one address cannot refer to two campuses, or a lookup
        # would resolve to whichever row was read first.
        UniqueConstraint("source_address", name="uq_campus_source_addresses_source_address"),
        Index("ix_campus_source_addresses_campus_id", "campus_id"),
    )

    id: Mapped[int] = pk_column()
    campus_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("campuses.id", ondelete="CASCADE"), nullable=False
    )
    source_address: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    campus: Mapped[Campus] = relationship(back_populates="source_addresses")


class CollegeCampus(Base):
    """An approved college/campus combination (COL-01).

    The composite primary key is the target of the composite foreign key on
    `course_offerings`, so "only a Campus approved for that College" is enforced
    by PostgreSQL rather than by application code.
    """

    __tablename__ = "college_campuses"
    # No extra UNIQUE on (college_id, campus_id): the composite PRIMARY KEY
    # already provides one, and PostgreSQL accepts a primary key as the target
    # of a composite foreign key. Declaring both left the model claiming a
    # constraint the database did not have, which `alembic check` correctly
    # reported as drift.

    college_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("colleges.id", ondelete="RESTRICT"), primary_key=True
    )
    campus_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("campuses.id", ondelete="RESTRICT"), primary_key=True
    )
    # Retire a combination without deleting it (DATA-03).
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    college: Mapped[College] = relationship(back_populates="campus_links")
    campus: Mapped[Campus] = relationship(back_populates="college_links")
