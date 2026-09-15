"""Students hold unverified references instead of being dropped.

Revision ID: a3c7f21e6b48
Revises: f1b8d5e73c94
Create Date: 2026-09-08

The approved rule, settled 8 September 2026:

    A row whose value does not verify against reference data is **stored and
    marked**, not discarded. A queue entry exists exactly when some stored row
    still carries such a value. Nothing behind an entry means no entry.

`allocation_delivery` has worked this way since it was built - it keeps
`college_text`, `campus_text`, `qualification_text` and `unit_text` beside
nullable identifiers, so an unmatched value is retained and repaired later by
resolving its suggestion, with no re-import. `students` could not: it has no
text columns and `course_offering_id` is NOT NULL, and a course offering is
derived from college + campus + qualification. So a student naming a campus TDMS
did not recognise could not be written at all, and the import dropped the row.

That made every student suggestion hollow. The queue entry was created at the
moment its rows were discarded, so it pointed at nothing from the start - the
interface offered "Map to approved record" over a value with, truthfully, zero
affected records. Two such entries covering 230 students sat in the queue while
those students were absent from the database entirely.

This migration gives students the same shape as deliveries:

* `course_offering_id` becomes nullable. It is filled in as soon as college,
  campus and qualification all resolve - by the import, or later by resolving
  the suggestion. Null means "not yet known", never "none".
* `college_text`, `campus_text` and `qualification_text` retain what the file
  said. They are kept after a successful resolve too, exactly as the delivery
  columns are: they record what the source actually contained.

**Unverified is not incomplete.** A row missing a required field is still
refused - this migration does not weaken that. It only stops a row being thrown
away for naming something reference data has not caught up with yet.

The unique rules need care. `uq_students_student_id_course_offering_id` is
UNIQUE on (student_id, course_offering_id), and in SQL two NULLs are distinct -
so with a nullable offering the same student could be written unverified any
number of times, once per import. PostgreSQL 15 added `NULLS NOT DISTINCT`,
which makes NULL compare equal here and restores the intent: one live row per
student per offering, with "no offering yet" counting as one offering. The
index is rebuilt rather than supplemented, so there is one rule, not two that
must agree.

`ck_students_offering_or_reference_text` is the safety net: a row without an
offering must say what it was trying to reach. Without it a bug could write a
student attached to nothing and describing nothing, which no later resolve
could ever repair.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a3c7f21e6b48"
down_revision = "f1b8d5e73c94"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "students",
        "course_offering_id",
        existing_type=sa.BigInteger(),
        nullable=True,
    )

    for column in ("college_text", "campus_text", "qualification_text"):
        op.add_column("students", sa.Column(column, sa.Text(), nullable=True))

    # Rebuilt with NULLS NOT DISTINCT so an unverified student cannot be
    # duplicated by re-importing the same file. See the module docstring.
    op.drop_index("uq_students_student_id_course_offering_id", table_name="students")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_students_student_id_course_offering_id
            ON students (student_id, course_offering_id)
            NULLS NOT DISTINCT
            WHERE is_deleted = false
        """
    )

    # A student with no offering must record what it was reaching for, or it can
    # never be repaired.
    op.create_check_constraint(
        "offering_or_reference_text",
        "students",
        "course_offering_id IS NOT NULL"
        " OR college_text IS NOT NULL"
        " OR campus_text IS NOT NULL"
        " OR qualification_text IS NOT NULL",
    )

    # No index is added for "students needing attention".
    # `ix_students_course_offering_id` is already partial on `is_deleted = false`
    # and a btree indexes NULLs, so it answers `course_offering_id IS NULL` on its
    # own. A second index on the same column would be redundant - which
    # `test_no_duplicate_indexes` catches.


def downgrade() -> None:
    # Rows stored only because the offering could be null cannot survive a
    # downgrade: there is no offering to give them and the column is about to be
    # NOT NULL again. They are removed rather than blocking the migration with a
    # constraint violation, which is why the upgrade is the safe direction.
    op.execute("DELETE FROM students WHERE course_offering_id IS NULL")

    # The naming convention in db/base.py supplies the `ck_students_` prefix, so
    # the bare name is passed here exactly as it is to create_check_constraint.
    op.drop_constraint("offering_or_reference_text", "students", type_="check")

    op.drop_index("uq_students_student_id_course_offering_id", table_name="students")
    op.execute(
        """
        CREATE UNIQUE INDEX uq_students_student_id_course_offering_id
            ON students (student_id, course_offering_id)
            WHERE is_deleted = false
        """
    )

    for column in ("qualification_text", "campus_text", "college_text"):
        op.drop_column("students", column)

    op.alter_column(
        "students",
        "course_offering_id",
        existing_type=sa.BigInteger(),
        nullable=False,
    )
