"""A trainer records the city they are based in.

Revision ID: f1b8d5e73c94
Revises: e7a1c4d92f38

Approved 27 August 2026. Adding a trainer by hand asks for the city — the
source file's `Trainer Campus` column, which is Sydney or Brisbane, not
Blacktown or Haymarket. Adding a full location (a campus with its weekdays and
working time) stays optional, so a trainer can be recorded before their timetable
is known.

Nullable, because the nine trainers already imported carry no city and inventing
one would be fabricating data. The service requires it on **create**; the column
does not, so an imported record without one is still storable and reads as
"City not recorded", the same way `campuses.city` behaves.

**No sequence object for the generated trainer id.** `TI_010_AY` is derived from
`MAX` over `trainers`, and the two rules fall out of that for free:

* A deleted trainer keeps its row (deletion is soft, DATA-04), so its number
  stays counted and is never handed to anyone else.
* Clearing the trainer database empties the table, so numbering restarts at 001
  — the approved behaviour, and impossible to get out of step with the rows the
  way a separate counter could.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f1b8d5e73c94"
down_revision = "e7a1c4d92f38"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("trainers", sa.Column("city", sa.Text(), nullable=True))
    op.create_index("ix_trainers_city", "trainers", ["city"])


def downgrade() -> None:
    op.drop_index("ix_trainers_city", table_name="trainers")
    op.drop_column("trainers", "city")
