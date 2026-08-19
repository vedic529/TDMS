"""Campus source addresses and superseded qualification codes

Approved 14 August 2026, after 306 of 1,158 real student rows failed to resolve
against reference data that was itself correct.

**Campus source addresses.** One physical campus is written several ways across
the source systems. Haymarket appears as both `841 George St, Haymarket NSW 2000`
and `Level 2, 8 Quay St, HAYMARKET, New South Wales 2000`; Melbourne has three
spellings; Brisbane's original `…Upper Mt Gravatt` was replaced by the corrected
`…Upper Mount Gravatt QLD 4122`. The import correctly merges these into one
campus — a site is one site — but only one spelling survived, so a student file
using any of the others could not resolve.

The campus keeps its single approved address. Every spelling that refers to it is
recorded here, so incoming data resolves whichever form it arrives in. The
alternative — a campus per spelling — would fracture one site into three and
break facility and clash checks that depend on a campus being a place.

**Superseded qualification codes.** `CHC30121` was superseded by `CHC30125`, and
`CHC52021` by `CHC52025`. Students enrolled under the old code are in the current
qualification. Mapping this in code would bury a business fact in a constant; it
is data, and it is recorded as data.

Direction matters and is enforced: `superseded_code` is the retired one, and the
foreign key points at the qualification that replaced it. A row can never say a
current code is superseded by itself, because the retired code is text and
deliberately not a foreign key — retired codes do not exist in `qualifications`.

Revision ID: b4e7c02a9f31
Revises: a92f4d7c1b58
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b4e7c02a9f31"
down_revision = "a92f4d7c1b58"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "campus_source_addresses",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("campus_id", sa.BigInteger(), nullable=False),
        sa.Column("source_address", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_campus_source_addresses")),
        sa.ForeignKeyConstraint(
            ["campus_id"],
            ["campuses.id"],
            name=op.f("fk_campus_source_addresses_campus_id_campuses"),
            ondelete="CASCADE",
        ),
        # Globally unique: one address string cannot refer to two campuses, or
        # incoming data would resolve to whichever row was read first.
        sa.UniqueConstraint("source_address", name=op.f("uq_campus_source_addresses_source_address")),
    )
    op.create_index(
        op.f("ix_campus_source_addresses_campus_id"), "campus_source_addresses", ["campus_id"]
    )

    op.create_table(
        "qualification_supersessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("superseded_code", sa.Text(), nullable=False),
        sa.Column("qualification_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_qualification_supersessions")),
        sa.ForeignKeyConstraint(
            ["qualification_id"],
            ["qualifications.id"],
            name=op.f("fk_qualification_supersessions_qualification_id_qualifications"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "superseded_code", name=op.f("uq_qualification_supersessions_superseded_code")
        ),
    )
    op.create_index(
        op.f("ix_qualification_supersessions_qualification_id"),
        "qualification_supersessions",
        ["qualification_id"],
    )

    for table in ("campus_source_addresses", "qualification_supersessions"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO tdms_app")
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO tdms_app")


def downgrade() -> None:
    # Both hold approved business facts that cannot be rebuilt from anything
    # else: an address spelling is not derivable, and a supersession is a
    # decision. Refuse rather than discard them silently.
    connection = op.get_bind()
    for table in ("campus_source_addresses", "qualification_supersessions"):
        stored = connection.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one()
        if stored:
            raise RuntimeError(
                f"Cannot downgrade: {table} holds {stored} approved row(s). "
                "They record decisions that cannot be recomputed. Remove them deliberately first."
            )

    op.drop_table("qualification_supersessions")
    op.drop_table("campus_source_addresses")
