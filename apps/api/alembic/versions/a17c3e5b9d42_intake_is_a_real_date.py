"""Intake is a real date, not a normalised first-of-month

Approved 12 August 2026 against the operational rolling timetable.

`0e8b41dd1b13` added `CHECK (EXTRACT(DAY FROM intake) = 1)` on the assumption
that intakes are monthly. The real BSB50420 rolling timetable disproves it: the
51 explicit intake markers fall on rolling start dates — 02-Feb-2026,
23-Feb-2026, 30-Mar-2026, 20-Apr-2026, 20-Jul-2026, 17-Aug-2026 and so on. Fifty
of the fifty-one would be rejected by that constraint, and normalising them to
the first of the month would move every intake off its actual start.

The column stays a native `date`. Only the constraint goes.

**No replacement rule is added.** Every observed marker happens to be a Monday,
because the workbook's calendar is Monday-aligned — but that is an observation
about one qualification's spreadsheet, not an approved rule about every intake
TDMS will ever hold. Turning it into a CHECK would swap one rule that rejects
real data for another that might. If a weekday rule is wanted it is a business
decision, and its own migration.

Display and export remain `DD-MMM-YYYY`; that is a presentation concern and was
never the database's business.

Revision ID: a17c3e5b9d42
Revises: c4a71f2d9b83
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a17c3e5b9d42"
down_revision = "c4a71f2d9b83"
branch_labels = None
depends_on = None

CONSTRAINT = "ck_student_groups_intake_is_first_of_month"


def upgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "student_groups", type_="check")


def downgrade() -> None:
    # Restoring the constraint would fail against any intake stored on its real
    # rolling date, and the alternative — quietly rewriting those dates to the
    # first of the month — would corrupt them. Refuse instead, naming the rows.
    connection = op.get_bind()
    offending = connection.execute(
        sa.text("SELECT count(*) FROM student_groups WHERE EXTRACT(DAY FROM intake) <> 1")
    ).scalar_one()
    if offending:
        raise RuntimeError(
            f"Cannot downgrade: {offending} student group(s) have an intake that is not "
            "the first of the month. Restoring the constraint would require changing "
            "real intake dates. Remove or correct those rows first."
        )

    op.create_check_constraint(
        "intake_is_first_of_month", "student_groups", "EXTRACT(DAY FROM intake) = 1"
    )
