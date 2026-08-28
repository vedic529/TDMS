"""Replace the pre-training-package rolling timetable table.

Revision ID: a8c2e19f4b70
Revises: d1f6a8c3e290
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a8c2e19f4b70"
down_revision = "d1f6a8c3e290"
branch_labels = None
depends_on = None

TRAINING_PACKAGES = ("CHC", "BSB", "FNS", "SIT", "AUR", "CPC", "ICT", "RII", "TLI", "UEE", "AHC")


def upgrade() -> None:
    op.drop_table("rolling_timetable_weeks")

    training_package = postgresql.ENUM(*TRAINING_PACKAGES, name="training_package", create_type=False)
    training_package.create(op.get_bind(), checkfirst=True)

    schedule_type = postgresql.ENUM(
        "UNIT", "BREAK", "ASSESSMENT_WEEK", name="rolling_schedule_type", create_type=False
    )

    op.create_table(
        "rolling_timetable_weeks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("training_package", training_package, nullable=False),
        sa.Column("qualification_code", sa.Text(), nullable=False),
        sa.Column("duration_weeks", sa.Integer(), nullable=False),
        sa.Column("intake_label", sa.Text(), nullable=False),
        sa.Column("intake_group", sa.Text(), nullable=False),
        sa.Column("intake_start_date", sa.Date(), nullable=False),
        sa.Column("week_no", sa.Integer(), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("week_end_date", sa.Date(), nullable=False),
        sa.Column("schedule_type", schedule_type, nullable=False),
        sa.Column("schedule_value", sa.Text(), nullable=False),
        sa.Column("unit_code", sa.Text(), nullable=True),
        sa.Column("unit_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unit_delivery_span_weeks", sa.Integer(), nullable=True),
        sa.Column("unit_slot", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint(
            "training_package::text = upper(left(qualification_code, 3))",
            name="training_package_matches_code",
        ),
        sa.CheckConstraint("week_end_date = week_start_date + 6", name="week_is_monday_to_sunday"),
        sa.CheckConstraint("duration_weeks > 0", name="rolling_duration_positive"),
        sa.CheckConstraint("week_no > 0", name="rolling_week_no_positive"),
        sa.CheckConstraint("unit_slot > 0", name="rolling_unit_slot_positive"),
        sa.CheckConstraint(
            "(schedule_type = 'UNIT' AND unit_code IS NOT NULL AND unit_count >= 1)"
            " OR (schedule_type <> 'UNIT' AND unit_code IS NULL AND unit_count = 0)",
            name="rolling_unit_fields_match_type",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rolling_timetable_weeks")),
        sa.UniqueConstraint(
            "training_package",
            "qualification_code",
            "duration_weeks",
            "intake_label",
            "week_no",
            "unit_slot",
            name="uq_rolling_timetable_weeks_loop_week_slot",
        ),
    )
    op.create_index(
        "ix_rolling_timetable_weeks_loop_week",
        "rolling_timetable_weeks",
        ["training_package", "qualification_code", "duration_weeks", "week_no"],
    )
    op.create_index("ix_rolling_timetable_weeks_intake_label", "rolling_timetable_weeks", ["intake_label"])
    op.create_index("ix_rolling_timetable_weeks_week_start_date", "rolling_timetable_weeks", ["week_start_date"])
    op.create_index("ix_rolling_timetable_weeks_unit_code", "rolling_timetable_weeks", ["unit_code"])


def downgrade() -> None:
    op.drop_index("ix_rolling_timetable_weeks_unit_code", table_name="rolling_timetable_weeks")
    op.drop_index("ix_rolling_timetable_weeks_week_start_date", table_name="rolling_timetable_weeks")
    op.drop_index("ix_rolling_timetable_weeks_intake_label", table_name="rolling_timetable_weeks")
    op.drop_index("ix_rolling_timetable_weeks_loop_week", table_name="rolling_timetable_weeks")
    op.drop_table("rolling_timetable_weeks")
    op.execute("DROP TYPE training_package")

    op.create_table(
        "rolling_timetable_weeks",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("qualification_code", sa.Text(), nullable=False),
        sa.Column("duration_weeks", sa.Integer(), nullable=False),
        sa.Column("intake_label", sa.Text(), nullable=False),
        sa.Column("intake_group", sa.Text(), nullable=False),
        sa.Column("intake_start_date", sa.Date(), nullable=False),
        sa.Column("week_no", sa.Integer(), nullable=False),
        sa.Column("week_start_date", sa.Date(), nullable=False),
        sa.Column("week_end_date", sa.Date(), nullable=False),
        sa.Column(
            "schedule_type",
            sa.Enum("UNIT", "BREAK", "ASSESSMENT_WEEK", name="rolling_schedule_type", create_type=False),
            nullable=False,
        ),
        sa.Column("schedule_value", sa.Text(), nullable=False),
        sa.Column("unit_code", sa.Text(), nullable=True),
        sa.Column("unit_code_2", sa.Text(), nullable=True),
        sa.Column("unit_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unit_delivery_span_weeks", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("week_end_date >= week_start_date", name="rolling_week_dates_ordered"),
        sa.CheckConstraint("duration_weeks > 0", name="rolling_duration_positive"),
        sa.CheckConstraint("week_no > 0", name="rolling_week_no_positive"),
        sa.CheckConstraint(
            "(schedule_type = 'UNIT' AND unit_code IS NOT NULL AND unit_count >= 1)"
            " OR (schedule_type <> 'UNIT' AND unit_code IS NULL AND unit_code_2 IS NULL"
            " AND unit_count = 0)",
            name="rolling_unit_fields_match_type",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_rolling_timetable_weeks")),
        sa.UniqueConstraint(
            "qualification_code",
            "duration_weeks",
            "intake_label",
            "week_no",
            name="uq_rolling_timetable_weeks_intake_week",
        ),
    )
    op.create_index(
        "ix_rolling_timetable_weeks_qualification_duration",
        "rolling_timetable_weeks",
        ["qualification_code", "duration_weeks"],
    )
    op.create_index("ix_rolling_timetable_weeks_intake_label", "rolling_timetable_weeks", ["intake_label"])
    op.create_index("ix_rolling_timetable_weeks_week_start_date", "rolling_timetable_weeks", ["week_start_date"])
    op.create_index("ix_rolling_timetable_weeks_unit_code", "rolling_timetable_weeks", ["unit_code"])
    op.create_index("ix_rolling_timetable_weeks_schedule_type", "rolling_timetable_weeks", ["schedule_type"])
