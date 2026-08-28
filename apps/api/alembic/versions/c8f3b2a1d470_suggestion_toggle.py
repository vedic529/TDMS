"""Suggestion toggle, nullable allocation FKs, suggestion matching keys.

Revision ID: c8f3b2a1d470
Revises: b7e4a91c2d80
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c8f3b2a1d470"
down_revision = "b7e4a91c2d80"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("allocation_delivery", "college_id", existing_type=sa.BigInteger(), nullable=True)
    op.alter_column("allocation_delivery", "campus_id", existing_type=sa.BigInteger(), nullable=True)
    op.alter_column("allocation_delivery", "qualification_id", existing_type=sa.BigInteger(), nullable=True)
    op.alter_column("allocation_delivery", "unit_id", existing_type=sa.BigInteger(), nullable=True)
    op.add_column(
        "allocation_import_batch",
        sa.Column("raise_suggestions", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column("reference_suggestion", sa.Column("normalised_value", sa.Text(), nullable=True))
    op.add_column("reference_suggestion", sa.Column("context_key", sa.Text(), nullable=True))
    op.add_column("reference_suggestion", sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        "UPDATE reference_suggestion SET normalised_value = upper(btrim(regexp_replace(raw_value, '\\s+', ' ', 'g'))), "
        "context_key = coalesce(context::text, '{}'), last_seen_at = first_seen_at"
    )
    op.alter_column("reference_suggestion", "normalised_value", nullable=False)
    op.alter_column("reference_suggestion", "context_key", nullable=False)
    op.execute("ALTER TYPE suggestion_status ADD VALUE IF NOT EXISTS 'REJECTED'")
    op.drop_constraint("uq_reference_suggestion_entity_raw_context", "reference_suggestion", type_="unique")
    op.create_unique_constraint(
        "uq_reference_suggestion_entity_normalised_context",
        "reference_suggestion",
        ["entity_type", "normalised_value", "context_key"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_reference_suggestion_entity_normalised_context", "reference_suggestion", type_="unique")
    op.create_unique_constraint(
        "uq_reference_suggestion_entity_raw_context",
        "reference_suggestion",
        ["entity_type", "raw_value", "context"],
    )
    op.drop_column("reference_suggestion", "last_seen_at")
    op.drop_column("reference_suggestion", "context_key")
    op.drop_column("reference_suggestion", "normalised_value")
    op.drop_column("allocation_import_batch", "raise_suggestions")
    op.alter_column("allocation_delivery", "unit_id", existing_type=sa.BigInteger(), nullable=False)
    op.alter_column("allocation_delivery", "qualification_id", existing_type=sa.BigInteger(), nullable=False)
    op.alter_column("allocation_delivery", "campus_id", existing_type=sa.BigInteger(), nullable=False)
    op.alter_column("allocation_delivery", "college_id", existing_type=sa.BigInteger(), nullable=False)
