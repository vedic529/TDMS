"""Trainer data backend: location dictionary, qualification-scoped units, offshore.

Revision ID: d94e6b3a2c15
Revises: e5d9c4b71a38

Puts the Trainer Data tab on the database. Four changes, each forced by the real
source file (`data/source/Trainer Data - BSB.xlsx`) rather than by design taste:

* **The Location Dictionary** extends `campuses` with `city` and
  `approved_address` (approved 26 August 2026). A parallel location table would
  split one place across two records and break the facility and clash checks,
  which depend on a campus being a single row. `campus_location` is deliberately
  left alone: the allocation importer's `campus_by_location` lookup and the
  export both read it, so changing its meaning would break both.

* **`trainer_units` gains `qualification_id`.** The same unit is legitimately
  taught under two qualifications — the real file contains 98 such pairs, for
  example `TI_001_AK` / `BSBPMG533` under both BSB40920 and BSB50820. Importing
  into the old `UNIQUE (trainer_id, unit_id)` would silently collapse them and
  destroy the qualification context.

* **A trainer may have no campus.** One row of the file reads Offshore, and
  `campus_id` was `NOT NULL`, so that trainer could not be stored at all. An
  offshore row is not a campus row with a missing campus; `is_offshore`
  distinguishes it from a campus that merely failed to resolve.

* **A trainer may be approved for both class types.** `Theory and Practical`
  means eligible for both, and the form already offered a third option the
  database could not store.

`qualification_id` is nullable because `trainer_units` already holds 180 rows
written before this change, which no `NOT NULL` could satisfy. Every row the
importer writes sets it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d94e6b3a2c15"
down_revision = "e5d9c4b71a38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- 2.1.1 The Location Dictionary ---------------------------------------
    # Both nullable: existing campuses have no city recorded, and inventing one
    # would be fabricating data. The dictionary reports "City not recorded".
    op.add_column("campuses", sa.Column("city", sa.Text(), nullable=True))
    op.add_column("campuses", sa.Column("approved_address", sa.Text(), nullable=True))
    op.create_index("ix_campuses_state_city", "campuses", ["state", "city"])

    # -- 2.1.2 A trainer's units are qualification-specific -------------------
    op.add_column("trainer_units", sa.Column("qualification_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        "fk_trainer_units_qualification_id_qualifications",
        "trainer_units",
        "qualifications",
        ["qualification_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.drop_constraint("uq_trainer_units_trainer_id_unit_id", "trainer_units", type_="unique")
    op.create_unique_constraint(
        "uq_trainer_units_trainer_qualification_unit",
        "trainer_units",
        ["trainer_id", "qualification_id", "unit_id"],
    )
    op.create_index("ix_trainer_units_qualification_id", "trainer_units", ["qualification_id"])

    # -- 2.1.3 Offshore availability -----------------------------------------
    op.alter_column(
        "trainer_availability", "campus_id", existing_type=sa.BigInteger(), nullable=True
    )
    # The raw `Location` value, kept only when the campus could not be resolved —
    # the same pattern `allocation_delivery.campus_text` uses. It is what lets an
    # unresolved campus be found again and repaired when the suggestion resolves.
    op.add_column("trainer_availability", sa.Column("location_text", sa.Text(), nullable=True))
    op.add_column(
        "trainer_availability",
        sa.Column("is_offshore", sa.Boolean(), nullable=False, server_default="false"),
    )
    # -- 2.1.5 The parsed times cannot hold `AEST/AEDT`, so the raw string stays.
    op.add_column("trainer_availability", sa.Column("working_time_text", sa.Text(), nullable=True))

    # The uniqueness rule must be rebuilt: the old constraint stops deduplicating
    # the moment `campus_id` is nullable, because PostgreSQL treats NULLs as
    # distinct and two offshore rows for one trainer would both be accepted.
    op.drop_constraint(
        "uq_trainer_availability_trainer_id_campus_id_class_type_start",
        "trainer_availability",
        type_="unique",
    )
    op.create_index(
        "uq_trainer_availability_campus",
        "trainer_availability",
        ["trainer_id", "campus_id", "class_type", "working_time_start"],
        unique=True,
        postgresql_where=sa.text("campus_id IS NOT NULL"),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_trainer_availability_no_campus "
        "ON trainer_availability (trainer_id, upper(btrim(location_text)), class_type, "
        "working_time_start) WHERE campus_id IS NULL"
    )
    # Offshore and "at a campus" are different states, not overlapping ones.
    op.create_check_constraint(
        "offshore_has_no_campus",
        "trainer_availability",
        "is_offshore = false OR campus_id IS NULL",
    )

    # -- 2.13 The shared staging stack serves a second consumer ---------------
    # Extended, not forked: the trainer importer reuses `import_batches`,
    # `import_staged_rows` and `import_row_issues` rather than adding a third
    # staging stack. All three columns are nullable, so the student importer is
    # unaffected and its rows keep reading exactly as they did.
    op.add_column("import_batches", sa.Column("data_type", sa.Text(), nullable=True))
    op.add_column("import_batches", sa.Column("apply_mode", sa.Text(), nullable=True))
    # The student rows carry typed `*_value` columns. A trainer row has a
    # different shape entirely, so its working values live here as JSON while
    # `raw_values` keeps the file's original cells for traceability.
    op.add_column(
        "import_staged_rows",
        sa.Column("working_values", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    # -- 2.1.4 The class-type value ------------------------------------------
    # A new enum value may not be *used* in the transaction that adds it, so it
    # is referenced nowhere else in this migration.
    op.execute("ALTER TYPE class_type ADD VALUE IF NOT EXISTS 'THEORY_AND_PRACTICAL'")
    # -- 2.13.4 So the shared queue can say where a suggestion came from.
    op.execute("ALTER TYPE suggestion_source ADD VALUE IF NOT EXISTS 'TRAINER_IMPORT'")


def downgrade() -> None:
    # An offshore row cannot be represented once `campus_id` is `NOT NULL`
    # again. Deleting it is stated here rather than left to fail halfway: there
    # is no campus to fall back to, and inventing one would be fabricating data.
    op.execute("DELETE FROM trainer_availability WHERE campus_id IS NULL")

    op.drop_constraint("offshore_has_no_campus", "trainer_availability", type_="check")
    op.drop_index("uq_trainer_availability_no_campus", table_name="trainer_availability")
    op.drop_index("uq_trainer_availability_campus", table_name="trainer_availability")
    op.create_unique_constraint(
        "uq_trainer_availability_trainer_id_campus_id_class_type_start",
        "trainer_availability",
        ["trainer_id", "campus_id", "class_type", "working_time_start"],
    )
    op.drop_column("trainer_availability", "working_time_text")
    op.drop_column("trainer_availability", "is_offshore")
    op.drop_column("trainer_availability", "location_text")
    op.alter_column(
        "trainer_availability", "campus_id", existing_type=sa.BigInteger(), nullable=False
    )

    # A unit taught under two qualifications collapses back to one row, so the
    # duplicates the old constraint cannot hold are removed first.
    op.execute(
        "DELETE FROM trainer_units a USING trainer_units b "
        "WHERE a.id > b.id AND a.trainer_id = b.trainer_id AND a.unit_id = b.unit_id"
    )
    op.drop_index("ix_trainer_units_qualification_id", table_name="trainer_units")
    op.drop_constraint(
        "uq_trainer_units_trainer_qualification_unit", "trainer_units", type_="unique"
    )
    op.create_unique_constraint(
        "uq_trainer_units_trainer_id_unit_id", "trainer_units", ["trainer_id", "unit_id"]
    )
    op.drop_constraint(
        "fk_trainer_units_qualification_id_qualifications", "trainer_units", type_="foreignkey"
    )
    op.drop_column("trainer_units", "qualification_id")

    op.drop_column("import_staged_rows", "working_values")
    op.drop_column("import_batches", "apply_mode")
    op.drop_column("import_batches", "data_type")

    op.drop_index("ix_campuses_state_city", table_name="campuses")
    op.drop_column("campuses", "approved_address")
    op.drop_column("campuses", "city")

    # `class_type.THEORY_AND_PRACTICAL` and `suggestion_source.TRAINER_IMPORT`
    # are left in place: PostgreSQL cannot remove an enum label, and recreating
    # the type would need every dependent column rewritten. This follows the
    # convention of f4a2c7e91b06 and e5d9c4b71a38.
