"""Display name is optional until Microsoft supplies it

Approved 13 August 2026, for direct user provisioning.

A Super Admin provisions an account with two facts: an organisational email and
an access level. They are not asked for the person's name, and TDMS must not
invent one — deriving "A. Chattopadhyay" from `a.chattopadhyay@` guesses at
capitalisation, word order, titles and which part is even a surname, then stores
the guess as though someone had confirmed it.

`display_name` was NOT NULL, which is what previously blocked seeding approved
users from their email addresses alone. It becomes nullable. NULL means "no
verified profile yet"; the interface renders that as *Awaiting Microsoft
profile*, which is a presentation state and is never written to the column.

The name is populated from verified Microsoft claims at first sign-in, when it
is a fact rather than a guess.

Revision ID: f3d81e6b0c47
Revises: e7b2c9a4f16d
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f3d81e6b0c47"
down_revision = "e7b2c9a4f16d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "display_name", existing_type=sa.Text(), nullable=True)


def downgrade() -> None:
    # Restoring NOT NULL would need a name for every pre-provisioned account,
    # and the only source would be the mailbox — the guess this migration exists
    # to prevent. Refuse and name the rows instead.
    connection = op.get_bind()
    awaiting = connection.execute(
        sa.text("SELECT count(*) FROM users WHERE display_name IS NULL")
    ).scalar_one()
    if awaiting:
        raise RuntimeError(
            f"Cannot downgrade: {awaiting} user(s) have no verified display name yet. "
            "Restoring NOT NULL would require deriving names from their email "
            "addresses. Wait until they have signed in, or remove those accounts."
        )

    op.alter_column("users", "display_name", existing_type=sa.Text(), nullable=False)
