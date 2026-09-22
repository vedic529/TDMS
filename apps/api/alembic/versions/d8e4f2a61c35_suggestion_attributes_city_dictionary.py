"""Suggestions carry their row's values; ROLLING and CITY entries; the City Dictionary.

Revision ID: d8e4f2a61c35
Revises: c9d3b6f52a81
Create Date: 2026-09-15

Three changes, approved 15 September 2026, when suggestions and exceptions were
separated: an unmatched value raises a suggestion and nothing else, and a broken
rule is edited or accepted and nothing else.

* **`reference_suggestion.attributes`.** Adding the record a suggestion names
  opens that tab's own form, and the form should arrive filled with everything
  the source row already said - a unit's title and UoC type, the campus a room
  was named at, the qualification a trainer was teaching. `context` cannot
  carry that: it is part of the deduplication key, so every extra value in it
  would split one entry into many. `attributes` sits beside it, outside the key.

* **`suggestion_entity_type` gains `ROLLING` and `CITY`.** A class the rolling
  timetable does not account for is resolved in the Rolling Timetable tab, and a
  city a file names that the City Dictionary does not hold is resolved in the
  dictionary. Both are unmatched values, so both are suggestions.

* **`cities`, the City Dictionary.** `campuses.city` was free text and empty on
  every row, so the trainer import's check that a trainer's city agrees with the
  campus they work at never ran. The dictionary is a separate table and
  `campuses.city` now references it by name - every reader of `campuses.city`
  keeps working, and renaming a city carries through to its campuses.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d8e4f2a61c35"
down_revision = "c9d3b6f52a81"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `IF NOT EXISTS` so a re-run is harmless. A value added here may not be
    # used in the same transaction, and nothing below uses it.
    op.execute("ALTER TYPE suggestion_entity_type ADD VALUE IF NOT EXISTS 'ROLLING'")
    op.execute("ALTER TYPE suggestion_entity_type ADD VALUE IF NOT EXISTS 'CITY'")

    op.add_column(
        "reference_suggestion",
        sa.Column(
            "attributes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )

    op.create_table(
        "cities",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("city_name", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cities")),
        sa.UniqueConstraint("city_name", name="uq_cities_city_name"),
    )

    # Any city a campus already names becomes a dictionary entry, so the key
    # below can be added without rewriting a campus. On the development database
    # no campus has one, and nothing is invented for them.
    op.execute(
        "INSERT INTO cities (city_name, state) "
        "SELECT DISTINCT ON (city) city, state FROM campuses WHERE city IS NOT NULL "
        "ORDER BY city, state"
    )

    # RESTRICT, not SET NULL: a city in use cannot be deleted out from under its
    # campuses. CASCADE on update is what makes a rename one change.
    op.create_foreign_key(
        op.f("fk_campuses_city_cities"),
        "campuses",
        "cities",
        ["city"],
        ["city_name"],
        onupdate="CASCADE",
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(op.f("fk_campuses_city_cities"), "campuses", type_="foreignkey")
    op.drop_table("cities")
    # PostgreSQL cannot drop an enum value. The entries using the two new values
    # are removed instead, so nothing holds a value the older code does not know.
    op.execute("DELETE FROM reference_suggestion WHERE entity_type::text IN ('ROLLING', 'CITY')")
    op.drop_column("reference_suggestion", "attributes")
