"""A unit can be practical only.

Revision ID: c9d3b6f52a81
Revises: b5e2c98a4d17
Create Date: 2026-09-10

`uoc_type` offered `THEORY` and `THEORY_AND_PRACTICAL`, so a unit that is
entirely practical had no honest value. The nearest choice was
`THEORY_AND_PRACTICAL`, which asserts theory the unit does not have and makes it
demand a theory room it never needs.

The system already knew the case existed. `uoc_type_allocation`, on
`allocation_delivery`, has held `THEORY_ONLY`, `PRACTICAL_ONLY` and
`THEORY_AND_PRACTICAL` since it was built - so a *class* could be scheduled as
practical only while the *unit* it delivers could not be described that way. The
two enums disagreed about what kinds of teaching exist.

`PRACTICAL` rather than `PRACTICAL_ONLY`, to match `THEORY` beside it. The
allocation enum keeps its own spelling: it describes how a delivery runs, not
what a unit is, and renaming a value in use would rewrite stored rows to settle
a question of style.

Not reversible in the usual sense. PostgreSQL cannot drop a value from an enum,
so the downgrade rebuilds the type without it - which means first deciding what
the rows using it become. They become `THEORY_AND_PRACTICAL`: the value that at
least admits practical delivery, and the one they would have been given before
this migration existed.
"""

from __future__ import annotations

from alembic import op

revision = "c9d3b6f52a81"
down_revision = "b5e2c98a4d17"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `IF NOT EXISTS` so a re-run is harmless. A value added here may not be
    # *used* in the same transaction, which is why nothing else in this
    # migration references it.
    op.execute("ALTER TYPE uoc_type ADD VALUE IF NOT EXISTS 'PRACTICAL'")


def downgrade() -> None:
    # An enum value cannot be dropped, so the type is rebuilt. Rows holding the
    # value being removed are moved to `THEORY_AND_PRACTICAL` first - the only
    # remaining value that admits practical delivery.
    op.execute(
        "UPDATE units SET uoc_type = 'THEORY_AND_PRACTICAL' WHERE uoc_type = 'PRACTICAL'"
    )
    op.execute("ALTER TYPE uoc_type RENAME TO uoc_type_old")
    op.execute("CREATE TYPE uoc_type AS ENUM ('THEORY', 'THEORY_AND_PRACTICAL')")
    op.execute(
        "ALTER TABLE units ALTER COLUMN uoc_type TYPE uoc_type "
        "USING uoc_type::text::uoc_type"
    )
    op.execute("DROP TYPE uoc_type_old")
