"""Facilities (TT-15).

Exactly the minimum set TT-15 requires and nothing beyond it, because OD-09
leaves the wider facility structure and the maintenance owner unapproved.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, CheckConstraint, ForeignKey, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, pk_column


class Facility(Base):
    """A room or resource used for timetable clash and capacity checking."""

    __tablename__ = "facilities"
    __table_args__ = (
        # DBQ-13: room codes are campus-scoped, so every site may have its own
        # `C1` without an artificial prefix.
        UniqueConstraint(
            "campus_id", "facility_reference", name="uq_facilities_campus_id_facility_reference"
        ),
        CheckConstraint("capacity > 0", name="capacity_positive"),
    )

    id: Mapped[int] = pk_column()
    facility_reference: Mapped[str] = mapped_column(Text, nullable=False)
    campus_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("campuses.id", ondelete="RESTRICT"), nullable=False
    )
    # Text, not an enum: OD-09 may extend the approved list of facility types.
    facility_type: Mapped[str] = mapped_column(Text, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    # DATA-03: never hard-deleted, so historical timetable rows stay readable.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
