"""Student data import: status, intake match, per-offering uniqueness, staging.

Revision ID: f4a2c7e91b06
Revises: c8f3b2a1d470

Supports the Student Data Import subsystem (25 August 2026):

* `student_status` and `student_intake_match` enum types.
* `STUDENT_IMPORT` added to the existing `suggestion_source` enum, so the shared
  reference-suggestion queue records unmatched student references without a
  second mechanism.
* `students` gains `status` and `intake_match_status`, and its global
  `student_id` UNIQUE (DBQ-08) is replaced by `(student_id, course_offering_id)`
  plus a partial unique index allowing at most one ACTIVE, non-deleted row per
  Student ID. This amends an approved decision to let one person hold more than
  one enrolment (rule 1.4).
* `import_staged_rows` gains the working, derived-preview and decision columns
  the 12-column student template needs, reusing the Schema v1 staging tables
  rather than creating a parallel one.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f4a2c7e91b06"
down_revision = "c8f3b2a1d470"
branch_labels = None
depends_on = None

_student_status = sa.Enum(
    "ACTIVE", "COMPLETED", "CANCELLED", "NOT_YET_STARTED", name="student_status"
)
_student_intake_match = sa.Enum("MATCHED", "TBD", "NOT_APPLICABLE", name="student_intake_match")

#: Reuse the types by name in add_column without trying to create them again.
_status_col = postgresql.ENUM(name="student_status", create_type=False)
_intake_match_col = postgresql.ENUM(name="student_intake_match", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    _student_status.create(bind, checkfirst=True)
    _student_intake_match.create(bind, checkfirst=True)
    # A new source value for the shared queue. Reversing an ADD VALUE is not
    # supported by PostgreSQL, so the downgrade leaves it in place (see below).
    op.execute("ALTER TYPE suggestion_source ADD VALUE IF NOT EXISTS 'STUDENT_IMPORT'")

    # -- students -----------------------------------------------------------
    op.add_column(
        "students",
        sa.Column("status", _status_col, nullable=False, server_default="ACTIVE"),
    )
    op.add_column(
        "students",
        sa.Column("intake_match_status", _intake_match_col, nullable=False, server_default="TBD"),
    )
    # Replace the global uniqueness with two narrower rules (1.4), both partial
    # on `is_deleted = false` so a soft-deleted record never blocks re-enrolment
    # (check D8).
    op.drop_constraint("uq_students_student_id", "students", type_="unique")
    op.create_index(
        "uq_students_student_id_course_offering_id",
        "students",
        ["student_id", "course_offering_id"],
        unique=True,
        postgresql_where=sa.text("is_deleted = false"),
    )
    op.create_index(
        "uq_students_one_active_enrolment",
        "students",
        ["student_id"],
        unique=True,
        postgresql_where=sa.text("status = 'ACTIVE' AND is_deleted = false"),
    )

    # -- import_staged_rows -------------------------------------------------
    op.add_column("import_staged_rows", sa.Column("ct_student_value", sa.Text(), nullable=True))
    op.add_column("import_staged_rows", sa.Column("status_value", sa.Text(), nullable=True))
    op.add_column("import_staged_rows", sa.Column("derived_intake_label", sa.Text(), nullable=True))
    op.add_column("import_staged_rows", sa.Column("derived_group_code", sa.Text(), nullable=True))
    op.add_column(
        "import_staged_rows",
        sa.Column("intake_match_status", _intake_match_col, nullable=True),
    )
    op.add_column("import_staged_rows", sa.Column("duplicate_scope", sa.Text(), nullable=True))
    # A plain pointer into the transient staging area, not a foreign key.
    op.add_column("import_staged_rows", sa.Column("existing_student_id", sa.BigInteger(), nullable=True))
    op.add_column("import_staged_rows", sa.Column("duplicate_decision", sa.Text(), nullable=True))
    op.add_column("import_staged_rows", sa.Column("existing_status_value", sa.Text(), nullable=True))
    op.add_column("import_staged_rows", sa.Column("college_choice", sa.Text(), nullable=True))
    op.add_column("import_staged_rows", sa.Column("campus_choice", sa.Text(), nullable=True))
    op.add_column("import_staged_rows", sa.Column("qualification_choice", sa.Text(), nullable=True))
    op.add_column(
        "import_staged_rows",
        sa.Column("excluded_by_user", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column("import_staged_rows", sa.Column("duration_override_weeks", sa.Integer(), nullable=True))


def downgrade() -> None:
    for column in (
        "duration_override_weeks",
        "excluded_by_user",
        "qualification_choice",
        "campus_choice",
        "college_choice",
        "existing_status_value",
        "duplicate_decision",
        "existing_student_id",
        "duplicate_scope",
        "intake_match_status",
        "derived_group_code",
        "derived_intake_label",
        "status_value",
        "ct_student_value",
    ):
        op.drop_column("import_staged_rows", column)

    op.drop_index("uq_students_one_active_enrolment", table_name="students")
    op.drop_index("uq_students_student_id_course_offering_id", table_name="students")
    op.create_unique_constraint("uq_students_student_id", "students", ["student_id"])
    op.drop_column("students", "intake_match_status")
    op.drop_column("students", "status")

    _student_intake_match.drop(op.get_bind(), checkfirst=True)
    _student_status.drop(op.get_bind(), checkfirst=True)
    # `STUDENT_IMPORT` stays in suggestion_source: PostgreSQL cannot drop one
    # enum value, and the earlier migrations follow the same one-way convention.
