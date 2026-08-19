"""Student groups and students (Schema v1 §8, §9)."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import enums
from app.db.base import Base, SoftDeleteMixin, TimestampMixin, pk_column, soft_delete_check


class StudentGroup(Base, TimestampMixin):
    """A student group — shared reference data, not free text (DBQ-10).

    SRS §5.3 sources Group from "approved student/group data", and the group
    appears on both student and timetable records. Making it an entity turns
    TT-06's student-group clash check into a foreign-key join rather than a
    string comparison, and gives Intake and Classroom Size a single home.

    Amended 11 August 2026 (Student Rules v1.1): `group_code` holds the approved
    numbered name — `Group 1`…`Group 15` — or `N/A` for a qualification that does
    not use groups.
    """

    __tablename__ = "student_groups"
    __table_args__ = (
        # A group name is unique WITHIN a course offering and intake, not
        # globally. "Group 1" has to exist for SIT40721/Aug-2026, for
        # SIT40721/Jan-2027 and for RII50520/Aug-2026 at the same time; a global
        # unique constraint would allow it to exist exactly once in the system.
        UniqueConstraint(
            "course_offering_id",
            "intake",
            "group_code",
            name="uq_student_groups_offering_intake_group_code",
        ),
        # Intake is the FIRST DAY of the proposed start month, so a mid-month
        # date is a bug rather than a variation worth storing.
        # No CHECK on `intake`: the operational rolling timetable puts intakes on
        # real rolling start dates (02-Feb-2026, 23-Feb-2026, 30-Mar-2026 ...),
        # not on the first of the month. See a17c3e5b9d42.
        #
        # Partial: the index serves lookups coming from the rolling timetable,
        # and the qualifications without one would otherwise fill it with nulls.
        Index(
            "ix_student_groups_rolling_intake_label",
            "rolling_intake_label",
            postgresql_where=text("rolling_intake_label IS NOT NULL"),
        ),
    )

    id: Mapped[int] = pk_column()
    group_code: Mapped[str] = mapped_column(Text, nullable=False)
    course_offering_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("course_offerings.id", ondelete="RESTRICT"), nullable=False
    )
    # The intake date. A real date, not formatted text — the approved
    # `DD-MMM-YYYY` form is applied at the display and export boundary, so
    # sorting and range filtering stay correct.
    #
    # The **fallback** identity. Where a rolling timetable exists,
    # `rolling_intake_label` below is authoritative; this remains because 69 of
    # the 82 qualifications have no rolling timetable and therefore no label, and
    # because a label cannot be ordered or rendered as a date.
    intake: Mapped[dt.date] = mapped_column(Date, nullable=False)
    #: The rolling timetable's own name for this cohort, verbatim —
    #: `BSB50420_52_9 Feb 2026_NA_Intake`.
    #:
    #: **Authoritative wherever it exists.** A rolling timetable week matches on
    #: this, never on the date: the label's date component is the first teaching
    #: week (9 Feb) while the intake's marked week began earlier (2 Feb), so
    #: converting between them lands on the wrong cohort.
    #:
    #: NULL for a qualification whose rolling timetable has not been supplied.
    rolling_intake_label: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        comment=(
            "Exact rolling timetable intake identifier, e.g. "
            "'BSB50420_52_9 Feb 2026_NA_Intake'. Authoritative cohort identity "
            "where a rolling timetable exists; NULL where one has not been supplied."
        ),
    )
    # SRS §5.3 Classroom Size — "Student/group data or authorised entry".
    expected_class_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    students: Mapped[list[Student]] = relationship(back_populates="student_group")


class Student(Base, SoftDeleteMixin, TimestampMixin):
    """One student record.

    Seven of the twenty-one SRS fields are deliberately **not** columns here —
    College, Campus, State, Qualification Code, Qualification Title and Intake
    are reached through foreign keys (DATA-02, proposal §8.1). The form is not
    the table.
    """

    __tablename__ = "students"
    __table_args__ = (
        CheckConstraint("proposed_end_date > proposed_start_date", name="course_dates_ordered"),
        soft_delete_check(),
        # Approved index recommendations (proposal §21). Partial on
        # `is_deleted = false` because every operational query excludes deleted
        # rows, which keeps the index smaller than a full one.
        Index(
            "ix_students_student_group_id",
            "student_group_id",
            postgresql_where=text("is_deleted = false"),
        ),
        Index(
            "ix_students_course_offering_id",
            "course_offering_id",
            postgresql_where=text("is_deleted = false"),
        ),
        Index("ix_students_last_name_first_name", "last_name", "first_name"),
    )

    id: Mapped[int] = pk_column()

    # DATA-01 / SST-05. UNIQUE across ALL rows including soft-deleted ones:
    # DBQ-08 approved that a Student ID is permanently reserved, so historical
    # activity records and import batches referencing it stay unambiguous.
    student_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)

    student_group_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("student_groups.id", ondelete="RESTRICT"), nullable=True
    )
    # Carries college, campus and qualification for this student.
    course_offering_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("course_offerings.id", ondelete="RESTRICT"), nullable=False
    )
    # Staff-selected approved option (DBQ-01). The FK guarantees the option
    # belongs to the student's own offering.
    course_duration_option_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("offering_duration_options.id", ondelete="RESTRICT"), nullable=True
    )

    college_email: Mapped[str] = mapped_column(CITEXT, nullable=False)
    first_name: Mapped[str] = mapped_column(Text, nullable=False)
    # SRS §6.1.3 Required = No.
    last_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    coe_status: Mapped[str] = mapped_column(enums.coe_status, nullable=False)

    proposed_start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    proposed_end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)

    # DBQ-01 approved the INCLUSIVE calculation. A generated column cannot drift
    # from the dates it derives from, which is what SRS §2.4 asks for: one
    # approved rule, shown consistently on screen, in exports and in storage.
    actual_course_duration_weeks: Mapped[int] = mapped_column(
        Integer,
        Computed(
            "(round((proposed_end_date - proposed_start_date + 1) / 7.0))::integer", persisted=True
        ),
        nullable=False,
    )

    # DBQ-01: a flag only. No transferred units, unit count or CT reference is
    # stored, and no duration reduction is derived from it.
    ct_student: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    personal_email: Mapped[str | None] = mapped_column(CITEXT, nullable=True)
    # No length: international phone formats vary.
    primary_phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    # OD-15 may later make this a foreign key to a controlled country list.
    primary_country: Mapped[str | None] = mapped_column(Text, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)

    student_group: Mapped[StudentGroup | None] = relationship(back_populates="students")
