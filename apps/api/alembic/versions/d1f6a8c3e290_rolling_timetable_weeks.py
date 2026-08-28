"""Rolling Timetable weeks — normalized Intake × Week requirements.

The approved source workbook is wide (one column per intake). SQL stores one
row per Intake and Week that carries a requirement. NA is not stored: absence
of a row is what NA means. Allocation tables are unchanged.

Revision ID: d1f6a8c3e290
Revises: c3f9a1d84b26
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d1f6a8c3e290"
down_revision = "c3f9a1d84b26"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
            sa.Enum("UNIT", "BREAK", "ASSESSMENT_WEEK", name="rolling_schedule_type"),
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


def downgrade() -> None:
    op.drop_index("ix_rolling_timetable_weeks_schedule_type", table_name="rolling_timetable_weeks")
    op.drop_index("ix_rolling_timetable_weeks_unit_code", table_name="rolling_timetable_weeks")
    op.drop_index("ix_rolling_timetable_weeks_week_start_date", table_name="rolling_timetable_weeks")
    op.drop_index("ix_rolling_timetable_weeks_intake_label", table_name="rolling_timetable_weeks")
    op.drop_index("ix_rolling_timetable_weeks_qualification_duration", table_name="rolling_timetable_weeks")
    op.drop_table("rolling_timetable_weeks")
    op.execute("DROP TYPE rolling_schedule_type")
