"""Bulk Student Import staging subsystem (Schema v1 §10).

Three tables. Uploaded data never touches `students` until the confirmed
transaction (BULK-02, BULK-08). This step creates the structure only — no CSV or
XLSX parsing, and no staged data.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import enums
from app.db.base import Base, pk_column


class ImportBatch(Base):
    """One uploaded student file and its result counts."""

    __tablename__ = "import_batches"

    id: Mapped[int] = pk_column()
    batch_reference: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # BULK-03: the uploading user must stay resolvable, hence RESTRICT.
    uploaded_by_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    #: Which kind of file this batch holds, for a consumer that accepts more
    #: than one shape — the trainer import's LOCATION or UNITS. NULL for the
    #: student import, which has a single template.
    data_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: MERGE or REPLACE, for a consumer that offers re-import modes.
    apply_mode: Mapped[str | None] = mapped_column(Text, nullable=True)

    # BULK-09: the six result counts. Stored on the batch because BULK-12
    # requires them in the activity record, and recomputing them later from rows
    # that have since changed would give a different answer.
    inserted_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    excluded_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duplicate_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    corrected_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rejected_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unmatched_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    rows: Mapped[list[ImportStagedRow]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", passive_deletes=True
    )


class ImportStagedRow(Base):
    """One uploaded row held in the staging area.

    Working values are `text`, not typed. A staged row exists precisely because
    the data may be invalid; typing the columns would reject the row before it
    could be shown to the user and corrected (BULK-05, BULK-06).
    """

    __tablename__ = "import_staged_rows"
    __table_args__ = (
        UniqueConstraint(
            "import_batch_id", "source_row_number", name="uq_import_staged_rows_import_batch_id_source_row_number"
        ),
        Index("ix_import_staged_rows_import_batch_id_status", "import_batch_id", "status"),
    )

    id: Mapped[int] = pk_column()
    import_batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_batches.id", ondelete="CASCADE"), nullable=False
    )
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    # The original cells exactly as uploaded, so a corrected row is still
    # traceable to what the file actually contained.
    raw_values: Mapped[dict] = mapped_column(JSONB, nullable=False)
    #: Working values for a consumer whose columns are not modelled as typed
    #: `*_value` columns below. The trainer importer corrects rows here while
    #: `raw_values` keeps what the file actually contained.
    working_values: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Working values, editable during correction (approved import template).
    # Every value is text: a staged row exists precisely because it may be
    # invalid, and typing the columns would reject the row before it could be
    # shown and corrected (BULK-05, BULK-06).
    student_id_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_name_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_name_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    college_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    campus_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualification_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    coe_status_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Added for the 12-column student import template (25 August 2026).
    ct_student_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    status_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_start_date_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    proposed_end_date_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    personal_email_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_phone_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    # BULK-04: set when the mapping matches approved reference data.
    resolved_college_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("colleges.id", ondelete="RESTRICT"), nullable=True
    )
    resolved_campus_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("campuses.id", ondelete="RESTRICT"), nullable=True
    )
    resolved_qualification_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("qualifications.id", ondelete="RESTRICT"), nullable=True
    )
    resolved_offering_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("course_offerings.id", ondelete="RESTRICT"), nullable=True
    )

    status: Mapped[str] = mapped_column(enums.staged_row_status, nullable=False)
    # DBQ-09: excluding the row is the only approved resolution, so a flag
    # replaces a resolution enum. It SURVIVES the exclusion, which matters
    # because BULK-09 needs both a duplicate count and an excluded count and one
    # row can belong to both.
    duplicate_detected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    corrected: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Sticky user exclusion (DBQ-09). Re-validation recomputes every other status
    # from the working values, but an explicit exclusion must survive it.
    excluded_by_user: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    # -- Derived preview (rule 2.5), shown before Confirm -------------------
    # The Intake and Group the system worked out from the rolling timetable, so
    # the preview shows what will be written before anything reaches `students`.
    derived_intake_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    derived_group_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    intake_match_status: Mapped[str | None] = mapped_column(enums.student_intake_match, nullable=True)
    # An approved Course Duration Option chosen by the user to resolve a TBD
    # intake (OD-08). It is used for the rolling-timetable lookup and stored as
    # the student's `course_duration_option_id`; the uploaded Proposed Start and
    # End dates, and the Actual Course Duration generated from them, are never
    # rewritten by it.
    duration_override_weeks: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # -- Duplicate handling (rule 2.6) -------------------------------------
    # SAME_QUALIFICATION or DIFFERENT_QUALIFICATION when this Student ID already
    # holds a stored record; NULL otherwise.
    duplicate_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    # The stored record this row conflicts with (same qualification), or the
    # stored ACTIVE record that a different-qualification enrolment collides with.
    # A plain pointer, not a foreign key: the staging area is scratch space that
    # is cleared on apply or abandon, and apply re-reads the student by id and
    # tolerates a missing one — so it needs neither SET NULL nor RESTRICT.
    existing_student_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    # Same qualification: KEEP_STORED or KEEP_INCOMING. Neither is chosen for the
    # user until they decide, so an undecided duplicate blocks the confirmation.
    duplicate_decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Different qualification: the new status to write on the conflicting stored
    # record, when the user resolves a two-ACTIVE collision by re-statusing it.
    existing_status_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    # -- Reference resolution (rule 2.4) -----------------------------------
    # Per entity: NULL (resolved or not yet decided), RAISE, EXCEPT, or RESOLVE.
    # RESOLVE fills the matching resolved_*_id above from an approved record.
    college_choice: Mapped[str | None] = mapped_column(Text, nullable=True)
    campus_choice: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualification_choice: Mapped[str | None] = mapped_column(Text, nullable=True)

    batch: Mapped[ImportBatch] = relationship(back_populates="rows")
    issues: Mapped[list[ImportRowIssue]] = relationship(
        back_populates="staged_row", cascade="all, delete-orphan", passive_deletes=True
    )


class ImportRowIssue(Base):
    """One validation problem on a staged row (BULK-05).

    A separate table rather than columns on the row: one row commonly has
    several independent problems, each needing its own field and message, and
    BULK-10 exports an issue report which is naturally one row per issue.
    """

    __tablename__ = "import_row_issues"

    id: Mapped[int] = pk_column()
    import_staged_row_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("import_staged_rows.id", ondelete="CASCADE"), nullable=False
    )
    field_name: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    issue_status: Mapped[str] = mapped_column(Text, nullable=False)

    staged_row: Mapped[ImportStagedRow] = relationship(back_populates="issues")
