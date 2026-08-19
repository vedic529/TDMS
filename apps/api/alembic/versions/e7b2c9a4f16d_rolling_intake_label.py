"""Rolling intake label is the authoritative cohort identity

Approved 13 August 2026.

A cohort is identified two ways. The rolling timetable names it —
`BSB50420_52_9 Feb 2026_NA_Intake` — and TDMS has until now known it only by a
date. The label becomes the **authoritative** identity: it is what a rolling
timetable week matches on, and it is the exact string the workbook carries.

`intake` stays a native `date`, for two reasons that are facts rather than
preferences:

* **Only 13 of the 82 qualifications have a rolling timetable.** The other 69 —
  every AHC, AUR, CHC, CPC, RII, SIT and ELICOS course — have no label to store.
  Dropping the date would leave their cohorts with no identity at all and make
  their students unrecordable.
* A label cannot be ordered, ranged or rendered as `DD-MMM-YYYY`. Those are date
  operations, and the approved display rule depends on them.

The two are also not interconvertible: column E's label reads `9 Feb 2026` — the
first teaching week — while the intake's marked week began `2 Feb 2026`.
Deriving one from the other lands on the wrong cohort.

So: the label leads wherever it exists, and the date remains the fallback. When
every rolling timetable has been supplied, `report_intakes_missing_a_label` in
`app.services.student_groups` will say so, and dropping the date becomes a safe
migration with evidence behind it. Doing it now would not be.

Revision ID: e7b2c9a4f16d
Revises: d58f1a4c7e93
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e7b2c9a4f16d"
down_revision = "d58f1a4c7e93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "student_groups",
        sa.Column(
            "rolling_intake_label",
            sa.Text(),
            nullable=True,
            comment=(
                "Exact rolling timetable intake identifier, e.g. "
                "'BSB50420_52_9 Feb 2026_NA_Intake'. Authoritative cohort identity "
                "where a rolling timetable exists; NULL where one has not been supplied."
            ),
        ),
    )
    # Partial: the index serves lookups from the rolling timetable, and the 69
    # qualifications without one would otherwise fill it with nulls.
    op.create_index(
        op.f("ix_student_groups_rolling_intake_label"),
        "student_groups",
        ["rolling_intake_label"],
        postgresql_where=sa.text("rolling_intake_label IS NOT NULL"),
    )


def downgrade() -> None:
    # The labels come from the workbook and are not recoverable from the date —
    # the two carry different dates for the same cohort. Refuse rather than
    # discard them silently.
    connection = op.get_bind()
    stored = connection.execute(
        sa.text(
            "SELECT count(*) FROM student_groups WHERE rolling_intake_label IS NOT NULL"
        )
    ).scalar_one()
    if stored:
        raise RuntimeError(
            f"Cannot downgrade: {stored} student group(s) carry a rolling intake label. "
            "The label cannot be rebuilt from the intake date. Re-import the rolling "
            "timetable after downgrading, or clear the labels first."
        )

    op.drop_index(
        op.f("ix_student_groups_rolling_intake_label"), table_name="student_groups"
    )
    op.drop_column("student_groups", "rolling_intake_label")
