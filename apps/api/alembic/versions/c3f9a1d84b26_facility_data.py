"""Facility Data — colleges, faculties and weekday availability

The supplied workbook has 129 rows, but a row is not a room. Profiling the file
answered the shape before any table was designed:

* Capacity, Classroom Type and State are **consistent per (Location, Classroom
  name)** — they are properties of the physical room. State is not stored here
  at all: `campuses.state` already carries it.
* Faculty, weekday availability and Remarks are **not** consistent per room, but
  availability and Remarks *are* consistent per (room, Faculty).
* College varies independently of Faculty. Colleges x Faculties per room
  reproduces exactly 129 rows, so the two are orthogonal and belong in two
  association tables rather than one wide one.

That gives 70 rooms, 110 room-college links and 81 room-faculty rules. Nothing
is lost and nothing is duplicated: the source file can be reconstructed from the
three tables exactly.

`facilities.source_location`
---------------------------
Two Hobart buildings sit on one campus — `Level 2, 132-146 Elizabeth Street` and
`Ground Floor, 142-146 Elizabeth Street` — and they share nine room names
(`Room 4`, `Room 5`, `Room 6`, `Room 10` and more). The existing
`UNIQUE(campus_id, facility_reference)` would have rejected them.

Splitting Hobart into two campuses would fracture a site that facility, trainer
and clash checks all treat as one place. Instead the supplied Location string is
kept verbatim on the facility and joins the uniqueness key. `Room 4` in each
building is then a distinct facility, both are preserved, and no relationship is
invented. Whether `142-146` is a second building or a typo for `132-146` is a
question for the project owner; until it is answered, keeping both is the only
option that cannot silently lose a room.

`facility_faculties.faculty`
----------------------------
Text, not an enum, matching `facilities.facility_type` — OD-09 leaves the wider
facility structure open. The column also holds two values the requirement's
prefix mapping does not cover: `ELICOS` (21 rows) and `NA` (2 rows). `NA` is a
business rule, not missing data, and is enforced in
`app.services.facilities.is_faculty_eligible`, not here.

Revision ID: c3f9a1d84b26
Revises: b4e7c02a9f31
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c3f9a1d84b26"
down_revision = "b4e7c02a9f31"
branch_labels = None
depends_on = None

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")


def upgrade() -> None:
    # ---------------------------------------------------------------- rooms
    # `facilities` is empty and no timetable session references one, so the key
    # can be widened directly rather than through a rebuild.
    op.add_column(
        "facilities",
        sa.Column("source_location", sa.Text(), nullable=False, server_default=""),
    )
    op.drop_constraint(
        "uq_facilities_campus_id_facility_reference", "facilities", type_="unique"
    )
    op.create_unique_constraint(
        op.f("uq_facilities_campus_id_source_location_facility_reference"),
        "facilities",
        ["campus_id", "source_location", "facility_reference"],
    )

    # ------------------------------------------------------------- colleges
    # Mirrors `college_campuses`: which college may use which room. A room is
    # shared — 33 of the 43 duplicate room names in the source differ by nothing
    # except the College column.
    op.create_table(
        "facility_colleges",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("facility_id", sa.BigInteger(), nullable=False),
        sa.Column("college_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_facility_colleges")),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name=op.f("fk_facility_colleges_facility_id_facilities"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["college_id"],
            ["colleges.id"],
            name=op.f("fk_facility_colleges_college_id_colleges"),
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "facility_id", "college_id", name=op.f("uq_facility_colleges_facility_id_college_id")
        ),
    )
    op.create_index(
        op.f("ix_facility_colleges_college_id"), "facility_colleges", ["college_id"]
    )

    # ------------------------------------------------ faculties + weekdays
    # Five named weekday columns, following `trainer_availability`. The source
    # is Yes/No so these are booleans rather than the `weekday_mode` enum that
    # trainers use.
    op.create_table(
        "facility_faculties",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("facility_id", sa.BigInteger(), nullable=False),
        sa.Column("faculty", sa.Text(), nullable=False),
        *(
            sa.Column(day, sa.Boolean(), nullable=False, server_default=sa.text("false"))
            for day in WEEKDAYS
        ),
        # NULL where the source said `NA` — that means "no relevant remark".
        # Informational only: no rule reads it (requirement section 13).
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_facility_faculties")),
        sa.ForeignKeyConstraint(
            ["facility_id"],
            ["facilities.id"],
            name=op.f("fk_facility_faculties_facility_id_facilities"),
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("length(btrim(faculty)) > 0", name="faculty_not_blank"),
        sa.UniqueConstraint(
            "facility_id", "faculty", name=op.f("uq_facility_faculties_facility_id_faculty")
        ),
    )
    op.create_index(op.f("ix_facility_faculties_faculty"), "facility_faculties", ["faculty"])

    for table in ("facility_colleges", "facility_faculties"):
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO tdms_app")
        op.execute(f"GRANT USAGE, SELECT ON SEQUENCE {table}_id_seq TO tdms_app")


def downgrade() -> None:
    # A facility's colleges and faculty rules are supplied business data that
    # cannot be recomputed from anything remaining. Refuse rather than discard.
    connection = op.get_bind()
    for table in ("facility_colleges", "facility_faculties"):
        stored = connection.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one()
        if stored:
            raise RuntimeError(
                f"Cannot downgrade: {table} holds {stored} supplied row(s). "
                "Remove them deliberately first."
            )

    op.drop_table("facility_faculties")
    op.drop_table("facility_colleges")

    # Narrowing the key back would silently drop one of two same-named rooms in
    # different buildings, so refuse while any such pair exists.
    clashes = connection.execute(
        sa.text(
            "SELECT count(*) FROM (SELECT campus_id, facility_reference FROM facilities "
            "GROUP BY campus_id, facility_reference HAVING count(*) > 1) AS d"
        )
    ).scalar_one()
    if clashes:
        raise RuntimeError(
            f"Cannot downgrade: {clashes} room name(s) exist in more than one building on the "
            "same campus. Narrowing the key would discard one of each pair."
        )

    op.drop_constraint(
        op.f("uq_facilities_campus_id_source_location_facility_reference"),
        "facilities",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_facilities_campus_id_facility_reference",
        "facilities",
        ["campus_id", "facility_reference"],
    )
    op.drop_column("facilities", "source_location")
