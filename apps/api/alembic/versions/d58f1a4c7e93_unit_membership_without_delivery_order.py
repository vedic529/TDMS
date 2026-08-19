"""Unit membership does not require a delivery order

Qualification Data states which units belong to a qualification. A rolling
timetable states the order they are delivered in. They are separate facts from
separate sources, and the second is not always available: of the 54
qualifications in the supplied Qualification Data, one — BSB50420 — currently has
an approved rolling timetable.

`delivery_order` was NOT NULL, so 1,048 real unit memberships could not be stored
at all without inventing a sequence for them. That is the wrong trade: an
invented 1..N looks exactly like an approved teaching order and would be acted on
as one.

The column becomes nullable. NULL means "membership known, delivery order not yet
supplied by an approved timetable source" — a fact, not a placeholder.

The uniqueness on (qualification_id, delivery_order) is unchanged and needs no
adjustment: PostgreSQL treats NULLs as distinct, so many units may sit in one
qualification awaiting an order while two units still cannot share position 3.
The constraint keeps its DEFERRABLE INITIALLY DEFERRED behaviour, so a whole
reorder still applies inside one transaction.

Revision ID: d58f1a4c7e93
Revises: a17c3e5b9d42
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d58f1a4c7e93"
down_revision = "a17c3e5b9d42"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "qualification_units",
        "delivery_order",
        existing_type=sa.Integer(),
        nullable=True,
    )


def downgrade() -> None:
    # Restoring NOT NULL would require a delivery order for every membership.
    # Filling them in would mean fabricating a teaching order for qualifications
    # that have no approved timetable — the thing this migration exists to stop —
    # so the downgrade refuses and names the rows instead.
    connection = op.get_bind()
    pending = connection.execute(
        sa.text("SELECT count(*) FROM qualification_units WHERE delivery_order IS NULL")
    ).scalar_one()
    if pending:
        raise RuntimeError(
            f"Cannot downgrade: {pending} unit membership row(s) have no delivery order. "
            "Restoring NOT NULL would require inventing a teaching sequence for "
            "qualifications with no approved rolling timetable. Supply the approved "
            "timetables, or remove those rows, then downgrade."
        )

    op.alter_column(
        "qualification_units",
        "delivery_order",
        existing_type=sa.Integer(),
        nullable=False,
    )
