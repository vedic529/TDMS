"""Use one canonical virtual classroom value.

Revision ID: a6f9c2d14b70
Revises: f5c1a8e3d920
Create Date: 2026-09-17

"Face to Face Virtual" and "Face to Face VC" describe the same classroom.
Existing virtual sessions and both accepted import spellings are normalised to
"Face to Face VC"; the redundant enum value is then removed.
"""

from __future__ import annotations

from alembic import op

revision = "a6f9c2d14b70"
down_revision = "f5c1a8e3d920"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE allocation_session
        SET virtual_kind = 'FACE_TO_FACE_VC',
            classroom_text = 'Face to Face VC'
        WHERE delivery_mode = 'VIRTUAL'
        """
    )
    op.execute("ALTER TYPE virtual_classroom_kind RENAME TO virtual_classroom_kind_old")
    op.execute("CREATE TYPE virtual_classroom_kind AS ENUM ('FACE_TO_FACE_VC')")
    op.execute(
        """
        ALTER TABLE allocation_session
        ALTER COLUMN virtual_kind TYPE virtual_classroom_kind
        USING virtual_kind::text::virtual_classroom_kind
        """
    )
    op.execute("DROP TYPE virtual_classroom_kind_old")


def downgrade() -> None:
    op.execute("ALTER TYPE virtual_classroom_kind RENAME TO virtual_classroom_kind_canonical")
    op.execute(
        "CREATE TYPE virtual_classroom_kind AS ENUM ('FACE_TO_FACE_VC', 'FACE_TO_FACE_VIRTUAL')"
    )
    op.execute(
        """
        ALTER TABLE allocation_session
        ALTER COLUMN virtual_kind TYPE virtual_classroom_kind
        USING virtual_kind::text::virtual_classroom_kind
        """
    )
    op.execute("DROP TYPE virtual_classroom_kind_canonical")
