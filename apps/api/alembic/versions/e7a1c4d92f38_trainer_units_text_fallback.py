"""Trainer units keep an unmatched qualification or unit as text.

Revision ID: e7a1c4d92f38
Revises: d94e6b3a2c15

Approved 27 August 2026, to match how the timetable import already behaves.

Raising a suggestion on the allocation import downgrades the blocker to a
warning and the row **imports**, keeping the raw value in `campus_text`,
`unit_text` and friends so a later resolution can find and repair it. The
trainer units import could not do the same: `trainer_units.unit_id` was
`NOT NULL` with a foreign key and no text column, so a unit the reference data
does not hold could not be stored at all, and every such row had to be excluded.

This mirrors `allocation_delivery` exactly:

* `unit_id` becomes nullable and gains `unit_text`.
* `qualification_text` joins the already-nullable `qualification_id`.
* A check on each pair, so a row always carries either the approved identifier
  or the raw value it was written as — never neither.
* The uniqueness rule is rebuilt as one expression index. The old
  `UNIQUE (trainer_id, qualification_id, unit_id)` stops deduplicating the
  moment `unit_id` is nullable, because PostgreSQL treats NULLs as distinct, so
  the same unmatched unit could be stored against one trainer many times.
* Normalised functional indexes so the relink comparison stays indexable,
  matching `ix_allocation_delivery_unit_text_norm`.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e7a1c4d92f38"
down_revision = "d94e6b3a2c15"
branch_labels = None
depends_on = None

#: The identity of a link, whichever half is resolved. Text is normalised the
#: same way the relink normalises it, and prefixed so a text value can never
#: collide with an id.
_KEY = (
    "trainer_id, "
    "coalesce(qualification_id::text, "
    "'t:' || upper(btrim(regexp_replace(qualification_text, '\\s+', ' ', 'g')))), "
    "coalesce(unit_id::text, "
    "'t:' || upper(btrim(regexp_replace(unit_text, '\\s+', ' ', 'g'))))"
)


def upgrade() -> None:
    op.alter_column("trainer_units", "unit_id", existing_type=sa.BigInteger(), nullable=True)
    op.add_column("trainer_units", sa.Column("unit_text", sa.Text(), nullable=True))
    op.add_column("trainer_units", sa.Column("qualification_text", sa.Text(), nullable=True))

    op.drop_constraint(
        "uq_trainer_units_trainer_qualification_unit", "trainer_units", type_="unique"
    )
    op.execute(f"CREATE UNIQUE INDEX uq_trainer_units_link ON trainer_units ({_KEY})")

    # Indexable relink comparisons, the same shape allocation_delivery uses.
    op.execute(
        "CREATE INDEX ix_trainer_units_unit_text_norm ON trainer_units "
        "(upper(btrim(regexp_replace(unit_text, '\\s+', ' ', 'g')))) "
        "WHERE unit_text IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX ix_trainer_units_qualification_text_norm ON trainer_units "
        "(upper(btrim(regexp_replace(qualification_text, '\\s+', ' ', 'g')))) "
        "WHERE qualification_text IS NOT NULL"
    )

    # A row always says what it means: an approved id, or the raw value.
    op.create_check_constraint(
        "unit_resolved_or_recorded",
        "trainer_units",
        "unit_id IS NOT NULL OR unit_text IS NOT NULL",
    )
    op.create_check_constraint(
        "qualification_resolved_or_recorded",
        "trainer_units",
        "qualification_id IS NOT NULL OR qualification_text IS NOT NULL",
    )


def downgrade() -> None:
    # A link with no approved unit cannot be represented once `unit_id` is
    # `NOT NULL` again, and there is no unit to fall back to. Stated here rather
    # than left to fail halfway.
    op.execute("DELETE FROM trainer_units WHERE unit_id IS NULL")

    op.drop_constraint("qualification_resolved_or_recorded", "trainer_units", type_="check")
    op.drop_constraint("unit_resolved_or_recorded", "trainer_units", type_="check")
    op.drop_index("ix_trainer_units_qualification_text_norm", table_name="trainer_units")
    op.drop_index("ix_trainer_units_unit_text_norm", table_name="trainer_units")
    op.drop_index("uq_trainer_units_link", table_name="trainer_units")

    # The old constraint cannot hold rows that differ only by a text value.
    op.execute(
        "DELETE FROM trainer_units a USING trainer_units b "
        "WHERE a.id > b.id AND a.trainer_id = b.trainer_id "
        "AND a.qualification_id IS NOT DISTINCT FROM b.qualification_id "
        "AND a.unit_id = b.unit_id"
    )
    op.create_unique_constraint(
        "uq_trainer_units_trainer_qualification_unit",
        "trainer_units",
        ["trainer_id", "qualification_id", "unit_id"],
    )
    op.drop_column("trainer_units", "qualification_text")
    op.drop_column("trainer_units", "unit_text")
    op.alter_column("trainer_units", "unit_id", existing_type=sa.BigInteger(), nullable=False)
