"""The Campus Address Dictionary: an address per college and campus.

Revision ID: f5c1a8e3d920
Revises: e2b7c4d19f63
Create Date: 2026-09-16

Approved 16 September 2026: a full address is identified by the combination of
college and campus, not by the campus alone. Haymarket is 8 Quay St for REACH and
NPA but 841 George St for AIBT and BIC; Melbourne is 620 Bourke St for REACH, 420
Collins St for AVTA and BIC, and 51 Brady St for NPA. A campus holds one
`campus_location`, so it could not say which.

The address lives on `college_campuses`, the approved combination itself. It is
nullable: a combination approved before the dictionary has no address, and
inventing one would be fabricating data.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f5c1a8e3d920"
down_revision = "e2b7c4d19f63"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("college_campuses", sa.Column("address", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("college_campuses", "address")
