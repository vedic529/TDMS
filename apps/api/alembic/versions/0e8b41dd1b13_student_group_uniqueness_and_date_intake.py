"""student group uniqueness and date intake

Approved 11 August 2026 (Step 5B). Two corrections to `student_groups`:

**1. `group_code` is no longer globally unique.** Under the approved Group rule
the codes are `Group 1`…`Group 15`, so a global UNIQUE would let `Group 1` exist
exactly once in the entire system. Uniqueness is per course offering and intake,
so all of these can coexist:

    SIT40721 / 01-Aug-2026 / Group 1
    SIT40721 / 01-Jan-2027 / Group 1
    RII50520 / 01-Aug-2026 / Group 1

**2. `intake` becomes a real `date`** holding the first day of the proposed start
month (`2026-08-01`). It was `text`, which sorts `01-Jan-2027` before
`01-Aug-2026` and cannot answer a date-range question. The approved
`DD-MMM-YYYY` display form is applied at the display and export boundary.

A CHECK constraint enforces that the stored date really is the first of the
month, so a mid-month value fails at write time rather than becoming quietly
wrong data.

`student_groups` was verified empty before this migration was written, so the
cast cannot lose anything. The `USING` clause still handles both the ISO and
`DD-MMM-YYYY` spellings, because a migration that only works on an empty table
is a migration that fails the first time it matters.

Revision ID: 0e8b41dd1b13
Revises: 805d65b129f2
Create Date: 2026-08-11

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0e8b41dd1b13"
down_revision: str | None = "805d65b129f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Drop the global uniqueness of the group name.
    # ------------------------------------------------------------------
    op.drop_constraint(op.f("uq_student_groups_group_code"), "student_groups", type_="unique")

    # ------------------------------------------------------------------
    # 2. text -> date.
    #
    # Done before the new UNIQUE is added, so the constraint is built on the
    # final column type rather than being rebuilt by the cast.
    # ------------------------------------------------------------------
    op.execute(
        """
        ALTER TABLE student_groups
        ALTER COLUMN intake TYPE date
        USING (
            CASE
                WHEN intake ~ '^\\d{4}-\\d{2}-\\d{2}$' THEN intake::date
                WHEN intake ~ '^\\d{1,2}-[A-Za-z]{3}-\\d{4}$' THEN to_date(intake, 'DD-Mon-YYYY')
            END
        )
        """
    )

    op.create_check_constraint(
        "intake_is_first_of_month", "student_groups", "EXTRACT(DAY FROM intake) = 1"
    )

    # ------------------------------------------------------------------
    # 3. Uniqueness per offering + intake + group name.
    # ------------------------------------------------------------------
    op.create_unique_constraint(
        op.f("uq_student_groups_offering_intake_group_code"),
        "student_groups",
        ["course_offering_id", "intake", "group_code"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("uq_student_groups_offering_intake_group_code"), "student_groups", type_="unique"
    )
    op.drop_constraint(op.f("ck_student_groups_intake_is_first_of_month"), "student_groups", type_="check")

    # date -> text, written back in ISO form so a re-upgrade parses it.
    op.execute(
        "ALTER TABLE student_groups ALTER COLUMN intake TYPE text USING to_char(intake, 'YYYY-MM-DD')"
    )

    # Restoring the global UNIQUE fails loudly if two offerings now share a
    # group name — which is the correct outcome: the data would not fit the old
    # shape, and silently dropping rows to make it fit would be worse.
    op.create_unique_constraint(
        op.f("uq_student_groups_group_code"), "student_groups", ["group_code"]
    )
