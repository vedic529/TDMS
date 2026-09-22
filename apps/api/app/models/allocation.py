"""Allocation records — partitioned deliveries and day-level sessions.

Replaces unused Schema v1 timetable_plans / unit_deliveries / sessions.
RollingTimetableWeek is unchanged and lives in timetable.py.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Identity,
    Index,
    Integer,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import enums
from app.db.base import Base, TimestampMixin, pk_column


class AllocationPackageProfile(Base):
    """Which training packages may be selected for import. Parsing rules stay in code."""

    __tablename__ = "allocation_package_profile"

    training_package: Mapped[str] = mapped_column(enums.training_package, primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class AllocationDelivery(Base, TimestampMixin):
    """One uploaded row: what is delivered. Partitioned by training_package."""

    __tablename__ = "allocation_delivery"
    __table_args__ = (
        UniqueConstraint(
            "training_package",
            "college_id",
            "campus_id",
            "qualification_id",
            "duration_weeks",
            "unit_id",
            "start_date",
            "end_date",
            name="uq_allocation_delivery_business_key",
        ),
        # `delivery_dates_ordered` was dropped on 15 September 2026: an end date
        # before the start is a rule the import checks, and one a person may
        # accept as an exception.
        CheckConstraint("duration_weeks > 0", name="allocation_duration_positive"),
        # Operational queries always exclude quarantined rows; a partial index
        # keeps them off the quarantined minority.
        Index(
            "ix_allocation_delivery_not_quarantined",
            "training_package",
            "campus_id",
            postgresql_where=text("is_quarantined = false"),
        ),
        # Relinking compares the normalised text, so the comparison must be
        # indexable or every resolution sequentially scans the table.
        Index(
            "ix_allocation_delivery_college_text_norm",
            text("upper(btrim(regexp_replace(college_text, '\s+', ' ', 'g')))"),
            postgresql_where=text("college_text IS NOT NULL"),
        ),
        Index(
            "ix_allocation_delivery_campus_text_norm",
            text("upper(btrim(regexp_replace(campus_text, '\s+', ' ', 'g')))"),
            postgresql_where=text("campus_text IS NOT NULL"),
        ),
        Index(
            "ix_allocation_delivery_qualification_text_norm",
            text("upper(btrim(regexp_replace(qualification_text, '\s+', ' ', 'g')))"),
            postgresql_where=text("qualification_text IS NOT NULL"),
        ),
        Index(
            "ix_allocation_delivery_unit_text_norm",
            text("upper(btrim(regexp_replace(unit_text, '\s+', ' ', 'g')))"),
            postgresql_where=text("unit_text IS NOT NULL"),
        ),
        {"postgresql_partition_by": "LIST (training_package)"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    training_package: Mapped[str] = mapped_column(enums.training_package, primary_key=True)
    college_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("colleges.id", ondelete="RESTRICT"), nullable=True
    )
    campus_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("campuses.id", ondelete="RESTRICT"), nullable=True
    )
    qualification_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("qualifications.id", ondelete="RESTRICT"), nullable=True
    )
    duration_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    group_code: Mapped[str] = mapped_column(Text, nullable=False)
    unit_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("units.id", ondelete="RESTRICT"), nullable=True
    )
    uoc_type: Mapped[str] = mapped_column(enums.uoc_type_allocation, nullable=False)
    mode_of_delivery: Mapped[str] = mapped_column(enums.allocation_mode_of_delivery, nullable=False)
    start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    classroom_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    intake_match_status: Mapped[str] = mapped_column(enums.intake_match_status, nullable=False)

    # -- Unresolved reference values, kept verbatim -------------------------
    # The same pattern `allocation_session` uses for `classroom_text` and
    # `trainer_text`: the value exactly as the file supplied it, written **only**
    # when the matching identifier could not be resolved. That is what lets the
    # row be found again and repaired when the value is later approved.
    #
    # An id and no text means resolved; text and no id means pending, excepted or
    # quarantined. The two are never both populated, so the state is unambiguous.
    college_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    campus_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    qualification_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # -- Quarantine (approved 26 August 2026) -------------------------------
    # Rejecting a structural reference value does not delete the rows that used
    # it. They are retained, marked here, and excluded from every operational
    # view, so a mistaken rejection stays recoverable and auditable.
    is_quarantined: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    quarantine_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    quarantined_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    quarantined_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )

    intakes: Mapped[list[AllocationDeliveryIntake]] = relationship(
        back_populates="delivery", cascade="all, delete-orphan"
    )
    sessions: Mapped[list[AllocationSession]] = relationship(back_populates="delivery")


class AllocationDeliveryIntake(Base):
    """Which rolling-timetable intakes attend a delivery."""

    __tablename__ = "allocation_delivery_intake"
    __table_args__ = (
        UniqueConstraint("delivery_id", "training_package", "intake_label", name="uq_allocation_delivery_intake"),
        ForeignKeyConstraint(
            ["delivery_id", "training_package"],
            ["allocation_delivery.id", "allocation_delivery.training_package"],
            ondelete="CASCADE",
            name="fk_allocation_delivery_intake_delivery",
        ),
        Index("ix_allocation_delivery_intake_intake_label", "intake_label"),
    )

    id: Mapped[int] = pk_column()
    delivery_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    training_package: Mapped[str] = mapped_column(enums.training_package, nullable=False)
    intake_label: Mapped[str] = mapped_column(Text, nullable=False)
    group_code: Mapped[str] = mapped_column(Text, nullable=False)

    delivery: Mapped[AllocationDelivery] = relationship(back_populates="intakes")


class AllocationSession(Base, TimestampMixin):
    """One stream on one weekday: when, where, who. Partitioned by training_package."""

    __tablename__ = "allocation_session"
    __table_args__ = (
        UniqueConstraint(
            "training_package",
            "delivery_id",
            "stream",
            "weekday",
            name="uq_allocation_session_delivery_stream_weekday",
        ),
        ForeignKeyConstraint(
            ["delivery_id", "training_package"],
            ["allocation_delivery.id", "allocation_delivery.training_package"],
            ondelete="CASCADE",
            name="fk_allocation_session_delivery",
        ),
        # Integrity, not a rule a file can break: a virtual class has no room.
        CheckConstraint(
            "delivery_mode <> 'VIRTUAL' OR facility_id IS NULL",
            name="virtual_has_no_facility",
        ),
        # The importer always stores MSCRIS as virtual, so that stays a check.
        # Its Saturday half, the Saturday rule for other streams, practical being
        # physical and a class ending after it starts were dropped on 15 September
        # 2026: each is a predefined rule the import checks, and a person may
        # accept a row that breaks one - which the database must then hold.
        CheckConstraint("stream <> 'MSCRIS' OR delivery_mode = 'VIRTUAL'", name="mscris_virtual"),
        Index("ix_allocation_session_package_weekday", "training_package", "weekday"),
        Index(
            "ix_allocation_session_facility_weekday",
            "facility_id",
            "weekday",
            postgresql_where=text("facility_id IS NOT NULL"),
        ),
        Index(
            "ix_allocation_session_trainer_weekday",
            "trainer_id",
            "weekday",
            postgresql_where=text("trainer_id IS NOT NULL"),
        ),
        Index("ix_allocation_session_delivery_id", "delivery_id"),
        # Relinking compares the normalised text (see the delivery indexes).
        Index(
            "ix_allocation_session_classroom_text_norm",
            text("upper(btrim(regexp_replace(classroom_text, '\s+', ' ', 'g')))"),
            postgresql_where=text("classroom_text IS NOT NULL"),
        ),
        Index(
            "ix_allocation_session_trainer_text_norm",
            text("upper(btrim(regexp_replace(trainer_text, '\s+', ' ', 'g')))"),
            postgresql_where=text("trainer_text IS NOT NULL"),
        ),
        {"postgresql_partition_by": "LIST (training_package)"},
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(), primary_key=True)
    training_package: Mapped[str] = mapped_column(enums.training_package, primary_key=True)
    delivery_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stream: Mapped[str] = mapped_column(enums.allocation_stream, nullable=False)
    weekday: Mapped[str] = mapped_column(enums.allocation_weekday, nullable=False)
    start_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    end_time: Mapped[dt.time] = mapped_column(Time, nullable=False)
    delivery_mode: Mapped[str] = mapped_column(enums.session_delivery_mode, nullable=False)
    facility_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("facilities.id", ondelete="RESTRICT"), nullable=True
    )
    virtual_kind: Mapped[str | None] = mapped_column(enums.virtual_classroom_kind, nullable=True)
    classroom_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    trainer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("trainers.id", ondelete="RESTRICT"), nullable=True
    )
    trainer_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    delivery: Mapped[AllocationDelivery] = relationship(back_populates="sessions")


class AllocationImportBatch(Base):
    __tablename__ = "allocation_import_batch"

    id: Mapped[int] = pk_column()
    training_package: Mapped[str] = mapped_column(enums.training_package, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    uploaded_by_user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    uploaded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    apply_mode: Mapped[str] = mapped_column(enums.apply_mode, nullable=False)
    rows_read: Mapped[int] = mapped_column(Integer, nullable=False)
    deliveries_written: Mapped[int] = mapped_column(Integer, nullable=False)
    sessions_written: Mapped[int] = mapped_column(Integer, nullable=False)
    deliveries_removed: Mapped[int] = mapped_column(Integer, nullable=False)
    suggestions_raised: Mapped[int] = mapped_column(Integer, nullable=False)
    raise_suggestions: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    completed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source_rows: Mapped[list[AllocationSourceRow]] = relationship(
        back_populates="batch", cascade="all, delete-orphan", passive_deletes=True
    )


class AllocationSourceRow(Base):
    """Audit copy of an uploaded row. Never read for display or download."""

    __tablename__ = "allocation_source_row"
    __table_args__ = (
        ForeignKeyConstraint(
            ["delivery_id", "training_package"],
            ["allocation_delivery.id", "allocation_delivery.training_package"],
            ondelete="SET NULL",
            name="fk_allocation_source_row_delivery",
        ),
        Index("ix_allocation_source_row_batch_id", "batch_id"),
    )

    id: Mapped[int] = pk_column()
    batch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("allocation_import_batch.id", ondelete="CASCADE"), nullable=False
    )
    training_package: Mapped[str | None] = mapped_column(enums.training_package, nullable=True)
    source_row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_values: Mapped[dict] = mapped_column(JSONB, nullable=False)
    delivery_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    batch: Mapped[AllocationImportBatch] = relationship(back_populates="source_rows")


class ReferenceSuggestion(Base):
    """Shared unmatched-reference queue for every tab."""

    __tablename__ = "reference_suggestion"
    __table_args__ = (
        UniqueConstraint(
            "entity_type", "normalised_value", "context_key", name="uq_reference_suggestion_entity_normalised_context"
        ),
        Index("ix_reference_suggestion_status_entity", "status", "entity_type"),
        # Serves the per-tab summary counts, which group by entity and status.
        Index("ix_reference_suggestion_entity_status", "entity_type", "status"),
    )

    id: Mapped[int] = pk_column()
    entity_type: Mapped[str] = mapped_column(enums.suggestion_entity_type, nullable=False)
    raw_value: Mapped[str] = mapped_column(Text, nullable=False)
    normalised_value: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    context_key: Mapped[str] = mapped_column(Text, nullable=False)
    #: The raising row's other values, for pre-filling the form Add opens
    #: (approved 15 September 2026): a unit's title, the campus a room was named
    #: at, the qualification a trainer was teaching. Outside the key - `context`
    #: decides which entry a value is, and every value added to it would split
    #: one entry into many. Lists accumulate across rows and imports.
    attributes: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    source: Mapped[str] = mapped_column(enums.suggestion_source, nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(enums.suggestion_status, nullable=False, server_default="PENDING")
    resolved_entity_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    resolved_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    resolved_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # -- Exception support (approved 26 August 2026) ------------------------
    # An accepted exception is this same row with `status = 'EXCEPTION'`. These
    # three columns are what a suggestion does not need: who allowed the value to
    # stand unapproved, when, and why. They are **retained** when an exception is
    # later promoted, so the record still shows it was once an exception.
    accepted_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    accepted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exception_note: Mapped[str | None] = mapped_column(Text, nullable=True)
