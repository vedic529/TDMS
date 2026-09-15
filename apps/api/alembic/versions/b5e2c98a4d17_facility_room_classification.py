"""Room classification becomes a column on the facility.

Revision ID: b5e2c98a4d17
Revises: a3c7f21e6b48
Create Date: 2026-09-09

The September revision of Facility Data added a `Room Classification` column -
`Computer Lab`, `Childcare Simulation Room`, `IS Simulation Room`,
`Electronics Room` - and `facilities` had nowhere to put it. The import kept the
value inside the faculty remark, prefixed `Room classification:`, which is how
the same fact had reached the database before: the August file wrote
`Source remarks: Electronics Room` for those rooms.

Nothing was lost that way, but nothing could use it either. A remark is free
text on a *faculty rule*, so the classification was attached to the wrong thing
(a room has one classification, whatever faculties use it) and could not be
filtered, matched or required. Timetabling cares whether a room is a computer
lab; it cannot ask a remark.

`room_classification` is nullable because most rooms have none - 108 of the 137
supplied rows leave it blank, and a plain classroom is not a defect. The column
is text rather than an enum: the four values are what the file happens to
contain today, not an approved list, and inventing an enum would make the next
unfamiliar value an import failure rather than a new kind of room.

The values already stored in remarks are moved here, and the prefix is stripped
from the remark so the same fact is not recorded twice and cannot drift. A
remark that carried *only* a classification becomes NULL rather than an empty
string - there is no remark left, and empty text pretending to be one would show
as a blank line in the interface.

Reversible: the downgrade puts the classification back into the remark in the
form the import wrote it, so a rollback loses nothing.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b5e2c98a4d17"
down_revision = "a3c7f21e6b48"
branch_labels = None
depends_on = None

#: The prefix the facility import used while the column did not exist.
PREFIX = "Room classification: "


def upgrade() -> None:
    op.add_column("facilities", sa.Column("room_classification", sa.Text(), nullable=True))

    # Lift the value onto the room it describes. `split_part` on the separator
    # the import used keeps whatever else the remark said.
    op.execute(
        f"""
        UPDATE facilities f
           SET room_classification = btrim(
                   split_part(substring(ff.remarks from {len(PREFIX) + 1}), ';', 1))
          FROM facility_faculties ff
         WHERE ff.facility_id = f.id
           AND ff.remarks LIKE '{PREFIX}%'
        """
    )

    # Remove it from the remark, and drop a remark that held nothing else.
    op.execute(
        f"""
        UPDATE facility_faculties
           SET remarks = nullif(
                   btrim(regexp_replace(remarks, '^{PREFIX}[^;]*;?\\s*', '')), '')
         WHERE remarks LIKE '{PREFIX}%'
        """
    )


def downgrade() -> None:
    # Put it back the way the import wrote it, in front of any other remark, so
    # nothing is lost by rolling back.
    op.execute(
        f"""
        UPDATE facility_faculties ff
           SET remarks = '{PREFIX}' || f.room_classification
                         || coalesce('; ' || ff.remarks, '')
          FROM facilities f
         WHERE f.id = ff.facility_id
           AND f.room_classification IS NOT NULL
        """
    )
    op.drop_column("facilities", "room_classification")
