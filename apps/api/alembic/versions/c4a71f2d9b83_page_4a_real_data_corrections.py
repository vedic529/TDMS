"""Page 4A real-data corrections: repeatable Course Code, optional Qualification Code

Two approved corrections, both forced by the real Page 4A export and neither
safe to work around in application code.

**1. `course_offerings.course_code` is no longer unique.**

Schema v1 assumed a Course Code identified one offering. The real export shows
163 of 183 Course Codes appearing at more than one Location — a CRICOS code
identifies the *course*, not the delivery of that course at one campus.

The offering's identity is unchanged and still enforced:
`UNIQUE (college_id, campus_id, qualification_id)` (COL-04). Only the redundant
and incorrect standalone constraint is removed. A non-unique index replaces it so
lookup by Course Code stays indexed.

**2. `qualifications.qualification_code` becomes nullable, unique where present.**

ELICOS courses have no VET Code. Four distinct course names arrive with `NA` or
blank, and a literal `'NA'` in each collides on a UNIQUE column.

"No code has been supplied" is stored as NULL and displayed as `NA`; the field
stays editable so an Admin can enter the real code when it is issued. Uniqueness
moves to a **partial** unique index over non-null values, so several ELICOS
qualifications can coexist while two qualifications still cannot share a real
code — which matters because the qualification code is the business key students,
trainers and timetables resolve against.

Revision ID: c4a71f2d9b83
Revises: 0e8b41dd1b13
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4a71f2d9b83"
down_revision = "0e8b41dd1b13"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- 1. Course Code may repeat across campuses -------------------------
    op.drop_constraint(
        op.f("uq_course_offerings_course_code"), "course_offerings", type_="unique"
    )
    op.create_index(
        op.f("ix_course_offerings_course_code"), "course_offerings", ["course_code"]
    )

    # --- 2. Qualification Code optional, unique only where supplied --------
    op.drop_constraint(
        op.f("uq_qualifications_qualification_code"), "qualifications", type_="unique"
    )
    op.alter_column(
        "qualifications",
        "qualification_code",
        existing_type=sa.Text(),
        nullable=True,
    )
    # A blank or 'NA' code means "not supplied" and must not occupy the value
    # space of a real code. Normalised before the partial index is created, so
    # existing rows cannot violate it.
    op.execute(
        "UPDATE qualifications SET qualification_code = NULL "
        "WHERE qualification_code IS NULL "
        "OR btrim(qualification_code) = '' "
        "OR upper(btrim(qualification_code)) IN ('NA', 'N/A')"
    )
    op.create_index(
        op.f("uq_qualifications_qualification_code"),
        "qualifications",
        ["qualification_code"],
        unique=True,
        postgresql_where=sa.text("qualification_code IS NOT NULL"),
    )


def downgrade() -> None:
    # Reversing 2 requires every qualification to have a code again. Rows
    # created without one cannot be given a real code here — inventing one is
    # exactly what this migration exists to avoid — so the downgrade refuses
    # rather than fabricating data.
    connection = op.get_bind()
    missing = connection.execute(
        sa.text("SELECT count(*) FROM qualifications WHERE qualification_code IS NULL")
    ).scalar_one()
    if missing:
        raise RuntimeError(
            f"Cannot downgrade: {missing} qualification(s) have no Qualification Code. "
            "Restoring NOT NULL would require inventing codes. Supply the approved "
            "codes first, then downgrade."
        )

    op.drop_index(op.f("uq_qualifications_qualification_code"), table_name="qualifications")
    op.alter_column(
        "qualifications",
        "qualification_code",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.create_unique_constraint(
        op.f("uq_qualifications_qualification_code"),
        "qualifications",
        ["qualification_code"],
    )

    op.drop_index(op.f("ix_course_offerings_course_code"), table_name="course_offerings")
    op.create_unique_constraint(
        op.f("uq_course_offerings_course_code"), "course_offerings", ["course_code"]
    )
