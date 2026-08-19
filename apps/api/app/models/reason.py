"""Controlled reason values (SRS §4.6, LOG-03; Schema v1 §16).

A lookup table rather than an enum on purpose: OD-06 leaves the final reason
list unapproved, and a lookup lets the approved list change without a schema
migration. No reason values are seeded here — seeding belongs to Step 4.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, pk_column


class ReasonCode(Base):
    """One approved reason for a delete, restore or override action."""

    __tablename__ = "reason_codes"

    id: Mapped[int] = pk_column()
    code: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    # LOG-03: "Other" requires a written explanation.
    requires_detail: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Retired, never deleted, so historical foreign keys keep resolving.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    display_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")

    contexts: Mapped[list[ReasonCodeContext]] = relationship(
        back_populates="reason_code", cascade="all, delete-orphan", passive_deletes=True
    )


class ReasonCodeContext(Base):
    """Where a reason may be offered, e.g. `STUDENT_DELETE`, `RESTORE`, `OVERRIDE`.

    Lets the approved list differ per action once OD-06 is settled, without a
    schema change.
    """

    __tablename__ = "reason_code_contexts"

    reason_code_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("reason_codes.id", ondelete="CASCADE"), primary_key=True
    )
    context: Mapped[str] = mapped_column(Text, primary_key=True)

    reason_code: Mapped[ReasonCode] = relationship(back_populates="contexts")
