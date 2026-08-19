"""Page 4A Course Data — the qualification offering (Schema v1 §7.2, §7.3).

Once qualification-level attributes are factored out into `qualifications`, what
remains of a Page 4A row **is** the offering. Creating both a `courses` table and
a separate `qualification_offerings` table would store the same relationship
twice and breach COL-04.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, pk_column, soft_delete_check


class CourseStatus(Base):
    """Course status lookup.

    A lookup rather than an enum because SRS §8.2 says a course may be "active,
    inactive, superseded **or in another approved status**" — an open-ended
    domain. No values are seeded here; that is Step 4.
    """

    __tablename__ = "course_statuses"

    id: Mapped[int] = pk_column()
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    # COL-05 / DATA-03 expressed as data: inactive and superseded values stay
    # visible for history but are not selectable for new records.
    selectable_for_new_records: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    offerings: Mapped[list[CourseOffering]] = relationship(back_populates="course_status")


class CourseOffering(Base, SoftDeleteMixin, TimestampMixin):
    """One qualification offered by one college at one campus."""

    __tablename__ = "course_offerings"
    __table_args__ = (
        # COL-04: the same approved college/campus/qualification offering must
        # not be stored more than once.
        UniqueConstraint(
            "college_id",
            "campus_id",
            "qualification_id",
            name="uq_course_offerings_college_id_campus_id_qualification_id",
        ),
        # COL-01 enforced by the database: one COMPOSITE foreign key, so an
        # offering cannot exist for a college/campus pair that was never
        # approved. Two separate FKs would permit an unapproved combination.
        ForeignKeyConstraint(
            ["college_id", "campus_id"],
            ["college_campuses.college_id", "college_campuses.campus_id"],
            ondelete="RESTRICT",
            name="fk_course_offerings_college_id_campus_id_college_campuses",
        ),
        Index("ix_course_offerings_college_id_campus_id", "college_id", "campus_id"),
        soft_delete_check(),
    )

    id: Mapped[int] = pk_column()
    # Page 4A "RTO" is this college (SRS §1.4, §8.2).
    college_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Page 4A "Location" is this campus (SRS §8.2).
    campus_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    qualification_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("qualifications.id", ondelete="RESTRICT"), nullable=False
    )
    # NOT unique: a CRICOS code identifies the course, not its delivery at one
    # campus, and the real Page 4A export repeats 163 of 183 codes across
    # campuses. Offering identity is the composite constraint above (COL-04).
    course_code: Mapped[str] = mapped_column(Text, index=True, nullable=False)
    course_status_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("course_statuses.id", ondelete="RESTRICT"), nullable=False
    )
    # numeric, not float: currency must not carry binary rounding error.
    # Nullable because OD-16 may remove Total Course Cost from scope entirely.
    total_course_cost: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    course_status: Mapped[CourseStatus] = relationship(back_populates="offerings")
    duration_options: Mapped[list[OfferingDurationOption]] = relationship(
        back_populates="course_offering", cascade="all, delete-orphan", passive_deletes=True
    )


class OfferingDurationOption(Base):
    """An approved duration for one offering (DBQ-03).

    A child table rather than a single `duration_weeks` column: COL-04 makes
    college+campus+qualification unique, so a 26-week and a 52-week version of
    the same qualification at the same campus cannot be separate offering rows.
    `students.course_duration_option_id` references this table, so the database
    guarantees a student can only be given a duration approved for their own
    offering.
    """

    __tablename__ = "offering_duration_options"
    __table_args__ = (
        UniqueConstraint(
            "course_offering_id",
            "duration_weeks",
            name="uq_offering_duration_options_course_offering_id_duration_weeks",
        ),
        CheckConstraint("duration_weeks > 0", name="duration_weeks_positive"),
    )

    id: Mapped[int] = pk_column()
    course_offering_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("course_offerings.id", ondelete="CASCADE"), nullable=False
    )
    duration_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    course_offering: Mapped[CourseOffering] = relationship(back_populates="duration_options")
