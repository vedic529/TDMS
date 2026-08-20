"""Facilities (TT-15) and the supplied Facility Data.

`Facility` is the physical room. What may use it is held alongside rather than
on it, because the supplied data proved the two are different grains: capacity
and type are the same for every row naming a room, while College and Faculty
vary and are independent of each other.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, pk_column

#: The weekday columns, in the order a timetable reads them. Named columns
#: rather than a row per day, following `trainer_availability`.
WEEKDAY_COLUMNS = ("monday", "tuesday", "wednesday", "thursday", "friday")


class Facility(Base):
    """A room used for timetable clash and capacity checking."""

    __tablename__ = "facilities"
    __table_args__ = (
        # DBQ-13: room names are site-scoped, so every campus may have its own
        # `Room 4`. `source_location` extends that one level further, because
        # two Hobart buildings on one campus share nine room names.
        UniqueConstraint(
            "campus_id",
            "source_location",
            "facility_reference",
            name="uq_facilities_campus_id_source_location_facility_reference",
        ),
        CheckConstraint("capacity > 0", name="capacity_positive"),
    )

    id: Mapped[int] = pk_column()
    facility_reference: Mapped[str] = mapped_column(Text, nullable=False)
    campus_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("campuses.id", ondelete="RESTRICT"), nullable=False
    )
    #: The Location string exactly as supplied. Kept verbatim so a room can be
    #: traced back to its source row, and so two buildings on one campus stay
    #: distinguishable without inventing a building code.
    source_location: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    # Text, not an enum: OD-09 may extend the approved list of facility types.
    facility_type: Mapped[str] = mapped_column(Text, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    # DATA-03: never hard-deleted, so historical timetable rows stay readable.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")

    #: String target: naming the class avoids importing `college` here and
    #: keeps the module import order free of a cycle.
    campus: Mapped["Campus"] = relationship("Campus", lazy="joined")  # noqa: F821

    colleges: Mapped[list[FacilityCollege]] = relationship(
        back_populates="facility", cascade="all, delete-orphan"
    )
    faculties: Mapped[list[FacilityFaculty]] = relationship(
        back_populates="facility", cascade="all, delete-orphan"
    )


class FacilityCollege(Base):
    """Which college may use a room.

    A room is shared: 33 of the 43 repeated room names in the supplied file
    differ by nothing except the College column. Modelled as a link table for
    the same reason `college_campuses` is — a college is not a property of a
    place, it is a permission over one.
    """

    __tablename__ = "facility_colleges"
    __table_args__ = (
        UniqueConstraint(
            "facility_id", "college_id", name="uq_facility_colleges_facility_id_college_id"
        ),
    )

    id: Mapped[int] = pk_column()
    facility_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    college_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("colleges.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    college: Mapped["College"] = relationship("College", lazy="joined")  # noqa: F821
    facility: Mapped[Facility] = relationship(back_populates="colleges")


class FacilityFaculty(Base):
    """A faculty permitted to use a room, and when.

    Availability sits here rather than on `Facility` because the supplied data
    showed it varying by faculty within the same room — ten rooms carry more
    than one faculty, each with its own weekday pattern. It is consistent for
    every (room, faculty) pair, which is exactly this grain.
    """

    __tablename__ = "facility_faculties"
    __table_args__ = (
        CheckConstraint("length(btrim(faculty)) > 0", name="faculty_not_blank"),
        UniqueConstraint(
            "facility_id", "faculty", name="uq_facility_faculties_facility_id_faculty"
        ),
    )

    id: Mapped[int] = pk_column()
    facility_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("facilities.id", ondelete="CASCADE"), nullable=False
    )
    #: As supplied. Includes `ELICOS`, which the approved prefix mapping does
    #: not cover, and `NA`, which means every faculty — a rule enforced in
    #: `app.services.facilities`, never by treating the value as missing.
    faculty: Mapped[str] = mapped_column(Text, nullable=False, index=True)

    monday: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    tuesday: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    wednesday: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    thursday: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    friday: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")

    #: NULL where the source said `NA`. Informational only — no rule reads it.
    remarks: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    facility: Mapped[Facility] = relationship(back_populates="faculties")

    def available_on(self, weekday: str) -> bool:
        """`weekday` is a `weekday` enum value such as `MONDAY`."""
        column = weekday.strip().lower()
        if column not in WEEKDAY_COLUMNS:
            raise ValueError(f"{weekday!r} is not a weekday this facility records")
        return bool(getattr(self, column))
