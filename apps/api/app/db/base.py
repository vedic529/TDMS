"""SQLAlchemy declarative base and shared column groups.

Implements the approved **Database Schema v1** (10 August 2026). The schema
documents under `docs/database/` are the source of truth; this module and the
model modules translate them into SQLAlchemy 2 declarative mappings.
"""

from __future__ import annotations

import datetime as dt

from sqlalchemy import BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKey, MetaData, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# ---------------------------------------------------------------------------
# Constraint naming convention (proposal §19)
# ---------------------------------------------------------------------------
# Applied centrally so Alembic renders predictable, reviewable names instead of
# PostgreSQL defaults. `%(column_0_N_name)s` truncates composite names to keep
# identifiers inside PostgreSQL's 63-character limit.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base for every TDMS model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


# ---------------------------------------------------------------------------
# Shared column groups
# ---------------------------------------------------------------------------


class TimestampMixin:
    """`created_at` / `updated_at` (proposal §24).

    Applied only to operationally edited tables. `created_by` / `updated_by` are
    deliberately absent everywhere: LOG-01/LOG-02 already record who did what,
    and a second, weaker audit trail could disagree with the first.
    """

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )


class SoftDeleteMixin:
    """Soft-deletion columns (SRS §2.3, DATA-04; proposal §17).

    Applied to operational records only — `students`, `course_offerings`,
    `qualification_units`, `trainers`, `timetable_plans`,
    `timetable_unit_deliveries`, `timetable_sessions`. Reference data ages
    through a status column instead (DATA-03, COL-05).

    The table-level CHECK added by :func:`soft_delete_check` is DATA-04 stated in
    SQL: a record cannot be soft-deleted without its full deletion metadata.
    """

    is_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    deleted_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    delete_reason_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("reason_codes.id", ondelete="RESTRICT"), nullable=True
    )
    delete_reason_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Stored rather than computed: the 14-day period is proposed, not approved,
    # so records deleted under the current period keep their original deadline.
    recovery_deadline: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


def soft_delete_check() -> CheckConstraint:
    """DATA-04: deletion metadata must be complete whenever `is_deleted` is true."""
    return CheckConstraint(
        "is_deleted = false OR ("
        "deleted_at IS NOT NULL AND deleted_by_user_id IS NOT NULL "
        "AND delete_reason_id IS NOT NULL AND recovery_deadline IS NOT NULL)",
        name="soft_delete_metadata_complete",
    )


def pk_column() -> Mapped[int]:
    """Internal primary key (proposal §18): `bigint GENERATED ALWAYS AS IDENTITY`.

    Business identifiers such as Student ID and Trainer ID are never primary
    keys; they are separate `UNIQUE NOT NULL` columns, so correcting a mistyped
    business code never has to cascade through dependent rows.
    """
    return mapped_column(BigInteger, primary_key=True, autoincrement=True)
