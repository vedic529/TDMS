"""Rolling timetable weeks. Allocation records live in allocation.py."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import CheckConstraint, Date, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import enums
from app.db.base import Base, TimestampMixin, pk_column


class RollingTimetableWeek(Base, TimestampMixin):
    """One Intake + Week that carries a rolling-timetable requirement.

    NA is never stored: absence of a row is what NA means. A clustered unit
    (slash in ``unit_code``) is one row. Two genuine units in one week use
    ``unit_slot`` 1 and 2.
    """

    __tablename__ = "rolling_timetable_weeks"
    __table_args__ = (
        UniqueConstraint(
            "training_package",
            "qualification_code",
            "duration_weeks",
            "intake_label",
            "week_no",
            "unit_slot",
            name="uq_rolling_timetable_weeks_loop_week_slot",
        ),
        CheckConstraint(
            "training_package::text = upper(left(qualification_code, 3))",
            name="training_package_matches_code",
        ),
        CheckConstraint("week_end_date = week_start_date + 6", name="week_is_monday_to_sunday"),
        CheckConstraint("duration_weeks > 0", name="rolling_duration_positive"),
        CheckConstraint("week_no > 0", name="rolling_week_no_positive"),
        CheckConstraint("unit_slot > 0", name="rolling_unit_slot_positive"),
        CheckConstraint(
            "(schedule_type = 'UNIT' AND unit_code IS NOT NULL AND unit_count >= 1)"
            " OR (schedule_type <> 'UNIT' AND unit_code IS NULL AND unit_count = 0)",
            name="rolling_unit_fields_match_type",
        ),
        Index(
            "ix_rolling_timetable_weeks_loop_week",
            "training_package",
            "qualification_code",
            "duration_weeks",
            "week_no",
        ),
        Index("ix_rolling_timetable_weeks_intake_label", "intake_label"),
        Index("ix_rolling_timetable_weeks_week_start_date", "week_start_date"),
        Index("ix_rolling_timetable_weeks_unit_code", "unit_code"),
    )

    id: Mapped[int] = pk_column()
    training_package: Mapped[str] = mapped_column(enums.training_package, nullable=False)
    qualification_code: Mapped[str] = mapped_column(Text, nullable=False)
    duration_weeks: Mapped[int] = mapped_column(Integer, nullable=False)
    intake_label: Mapped[str] = mapped_column(Text, nullable=False)
    intake_group: Mapped[str] = mapped_column(Text, nullable=False)
    intake_start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    week_no: Mapped[int] = mapped_column(Integer, nullable=False)
    week_start_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    week_end_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    schedule_type: Mapped[str] = mapped_column(enums.rolling_schedule_type, nullable=False)
    schedule_value: Mapped[str] = mapped_column(Text, nullable=False)
    unit_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    unit_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    unit_delivery_span_weeks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_slot: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
