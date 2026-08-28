"""Suggestion relink text, quarantine, and recorded exceptions.

Revision ID: e5d9c4b71a38
Revises: f4a2c7e91b06

Establishes the invariant that every stored reference value is either an
approved identifier, a recorded exception, or a quarantined rejection:

* `allocation_delivery` gains four text fallback columns, mirroring the pattern
  `allocation_session` already uses, so a value that could not be resolved is
  kept verbatim and the row can be found and repaired later. Without them a
  resolution had nothing to match on, which is why four of the six entity types
  silently relinked nothing.
* `allocation_delivery` gains quarantine columns. Rejecting a structural value
  retains its rows and hides them from operational views instead of deleting
  them (approved 26 August 2026).
* `reference_suggestion` gains the columns an accepted exception needs, and
  `suggestion_status` gains `EXCEPTION` and `WITHDRAWN`.
* Functional indexes so the normalised relink comparisons stay indexable.

No backfill: rows imported before this migration carry no text and cannot be
repaired retroactively (approved decision 1.7).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e5d9c4b71a38"
down_revision = "f4a2c7e91b06"
branch_labels = None
depends_on = None

#: (index name, table, column) for the normalised-text functional indexes.
_TEXT_INDEXES = (
    ("ix_allocation_delivery_college_text_norm", "allocation_delivery", "college_text"),
    ("ix_allocation_delivery_campus_text_norm", "allocation_delivery", "campus_text"),
    ("ix_allocation_delivery_qualification_text_norm", "allocation_delivery", "qualification_text"),
    ("ix_allocation_delivery_unit_text_norm", "allocation_delivery", "unit_text"),
    ("ix_allocation_session_classroom_text_norm", "allocation_session", "classroom_text"),
    ("ix_allocation_session_trainer_text_norm", "allocation_session", "trainer_text"),
)


def upgrade() -> None:
    # -- Text fallbacks -----------------------------------------------------
    # `allocation_delivery` is PARTITION BY LIST (training_package); adding a
    # column on the parent propagates to every partition, so they are never
    # altered individually.
    for column in ("college_text", "campus_text", "qualification_text", "unit_text"):
        op.add_column("allocation_delivery", sa.Column(column, sa.Text(), nullable=True))

    # -- Quarantine ---------------------------------------------------------
    op.add_column(
        "allocation_delivery",
        sa.Column("is_quarantined", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("allocation_delivery", sa.Column("quarantine_reason", sa.Text(), nullable=True))
    op.add_column(
        "allocation_delivery",
        sa.Column("quarantined_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "allocation_delivery",
        sa.Column("quarantined_by_user_id", sa.BigInteger(), nullable=True),
    )
    op.create_foreign_key(
        "fk_allocation_delivery_quarantined_by_user_id_users",
        "allocation_delivery",
        "users",
        ["quarantined_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_allocation_delivery_not_quarantined",
        "allocation_delivery",
        ["training_package", "campus_id"],
        postgresql_where=sa.text("is_quarantined = false"),
    )

    # -- Exception support on the shared queue ------------------------------
    # A new enum value may not be USED in the transaction that adds it, so
    # nothing below references 'EXCEPTION'.
    op.execute("ALTER TYPE suggestion_status ADD VALUE IF NOT EXISTS 'EXCEPTION'")
    op.execute("ALTER TYPE suggestion_status ADD VALUE IF NOT EXISTS 'WITHDRAWN'")

    op.add_column(
        "reference_suggestion",
        sa.Column("accepted_by_user_id", sa.BigInteger(), nullable=True),
    )
    op.add_column(
        "reference_suggestion",
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("reference_suggestion", sa.Column("exception_note", sa.Text(), nullable=True))
    op.create_foreign_key(
        "fk_reference_suggestion_accepted_by_user_id_users",
        "reference_suggestion",
        "users",
        ["accepted_by_user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_reference_suggestion_entity_status",
        "reference_suggestion",
        ["entity_type", "status"],
    )

    # -- Case-insensitive matching support ----------------------------------
    for name, table, column in _TEXT_INDEXES:
        # Must match the expression `reference_suggestion_service._normalised`
        # builds, including the internal-whitespace collapse, or the comparison
        # cannot use the index.
        op.execute(
            f"CREATE INDEX {name} ON {table} "
            f"(upper(btrim(regexp_replace({column}, '\s+', ' ', 'g')))) "
            f"WHERE {column} IS NOT NULL"
        )


def downgrade() -> None:
    for name, _table, _column in _TEXT_INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")

    op.drop_index("ix_reference_suggestion_entity_status", table_name="reference_suggestion")
    op.drop_constraint(
        "fk_reference_suggestion_accepted_by_user_id_users", "reference_suggestion", type_="foreignkey"
    )
    op.drop_column("reference_suggestion", "exception_note")
    op.drop_column("reference_suggestion", "accepted_at")
    op.drop_column("reference_suggestion", "accepted_by_user_id")

    op.drop_index("ix_allocation_delivery_not_quarantined", table_name="allocation_delivery")
    op.drop_constraint(
        "fk_allocation_delivery_quarantined_by_user_id_users", "allocation_delivery", type_="foreignkey"
    )
    for column in (
        "quarantined_by_user_id",
        "quarantined_at",
        "quarantine_reason",
        "is_quarantined",
        "unit_text",
        "qualification_text",
        "campus_text",
        "college_text",
    ):
        op.drop_column("allocation_delivery", column)

    # `EXCEPTION` and `WITHDRAWN` stay in `suggestion_status`: PostgreSQL cannot
    # remove a single enum value, and the earlier migrations follow the same
    # one-way convention.
