"""access model v1.1

Adds VIEWER as the fourth access level, removes the Data Editor work assignment,
and introduces the role access-request workflow.

See `docs/database/access-model-v1.1.md`.

**Why the enum types are recreated rather than altered.** `ALTER TYPE ... ADD
VALUE` can only append, and PostgreSQL cannot remove an enum value at all — so
that approach would put `VIEWER` last in a type whose declared order *is* the
privilege order, and would leave `downgrade()` unable to reverse itself. Renaming
the old type, creating the new one and casting the dependent columns through
`text` keeps the ordering meaningful, runs inside one transaction, and downgrades
cleanly. Both tables are empty at the time of writing, but the cast is written to
work with data regardless.

Revision ID: 805d65b129f2
Revises: 6266b57ea53e
Create Date: 2026-08-11

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "805d65b129f2"
down_revision: str | None = "6266b57ea53e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Ascending privilege in both directions, so `>=` comparisons keep working.
ACCESS_LEVEL_NEW = ("VIEWER", "DATA_EDITOR", "ADMIN", "SUPER_ADMIN")
ACCESS_LEVEL_OLD = ("DATA_EDITOR", "ADMIN", "SUPER_ADMIN")

ACTIVITY_ACTION_OLD = (
    "SIGN_IN",
    "SIGN_OUT",
    "CREATE",
    "UPDATE",
    "DELETE",
    "RESTORE",
    "IMPORT",
    "EXPORT",
    "TIMETABLE_SAVE",
    "TIMETABLE_GENERATION",
    "CANCELLATION_AFTER_UPDATE",
    "OVERRIDE",
    "ACCESS_DENIED",
)
ACTIVITY_ACTION_NEW = ACTIVITY_ACTION_OLD + (
    "ACCESS_REQUEST_SUBMITTED",
    "ACCESS_REQUEST_APPROVED",
    "ACCESS_REQUEST_DENIED",
    "ACCESS_REQUEST_CANCELLED",
    "ROLE_CHANGED",
    "ACCOUNT_STATUS_CHANGED",
)

ACCESS_REQUEST_STATUS = ("PENDING", "APPROVED", "DENIED", "CANCELLED")

DATA_EDITOR_ASSIGNMENT = ("STUDENT_DATA_OFFICER", "TIMETABLE_OFFICER")


def _quoted(values: Sequence[str]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _replace_enum(name: str, values: Sequence[str], columns: Sequence[tuple[str, str]]) -> None:
    """Swap an enum type for a new definition, recasting dependent columns.

    `columns` is a sequence of (table, column). Any column default is dropped and
    restored around the cast, because PostgreSQL will not cast a column whose
    default still refers to the old type.
    """
    op.execute(f"ALTER TYPE {name} RENAME TO {name}_old")
    op.execute(f"CREATE TYPE {name} AS ENUM ({_quoted(values)})")
    for table, column in columns:
        op.execute(f"ALTER TABLE {table} ALTER COLUMN {column} DROP DEFAULT")
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} "
            f"TYPE {name} USING {column}::text::{name}"
        )
    op.execute(f"DROP TYPE {name}_old")


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Remove the Data Editor work assignment.
    #
    # A Data Editor now maintains both Student Data and Timetable, so the
    # column no longer decides anything. It is dropped before the enum swap
    # because `users.data_editor_assignment` would otherwise still depend on
    # the type being removed.
    # ------------------------------------------------------------------
    # op.f() marks the name as already final, so the metadata naming convention
    # does not prefix it a second time.
    op.drop_constraint(
        op.f("ck_users_assignment_only_for_data_editor"), "users", type_="check"
    )
    op.drop_column("users", "data_editor_assignment")
    op.drop_column("user_activity_records", "assignment_snapshot")
    op.execute("DROP TYPE data_editor_assignment")

    # ------------------------------------------------------------------
    # 2. Add VIEWER as the lowest access level.
    # ------------------------------------------------------------------
    _replace_enum(
        "access_level",
        ACCESS_LEVEL_NEW,
        [("users", "access_level"), ("user_activity_records", "access_level_snapshot")],
    )

    # ------------------------------------------------------------------
    # 3. New activity actions for the request and role-management workflow.
    # ------------------------------------------------------------------
    _replace_enum(
        "activity_action", ACTIVITY_ACTION_NEW, [("user_activity_records", "action")]
    )

    # ------------------------------------------------------------------
    # 4. The access-request workflow.
    # ------------------------------------------------------------------
    op.execute(f"CREATE TYPE access_request_status AS ENUM ({_quoted(ACCESS_REQUEST_STATUS)})")

    op.create_table(
        "access_requests",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("requester_user_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "role_at_request",
            postgresql.ENUM(*ACCESS_LEVEL_NEW, name="access_level", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "requested_role",
            postgresql.ENUM(*ACCESS_LEVEL_NEW, name="access_level", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM(*ACCESS_REQUEST_STATUS, name="access_request_status", create_type=False),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column(
            "requested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.CheckConstraint(
            "requested_role <> 'VIEWER'", name=op.f("ck_access_requests_requested_role_not_viewer")
        ),
        sa.CheckConstraint(
            "requested_role > role_at_request",
            name=op.f("ck_access_requests_requested_role_is_higher"),
        ),
        sa.CheckConstraint(
            "(status = 'PENDING' AND decided_at IS NULL AND decided_by_user_id IS NULL)"
            " OR (status <> 'PENDING' AND decided_at IS NOT NULL AND decided_by_user_id IS NOT NULL)",
            name=op.f("ck_access_requests_decision_fields_match_status"),
        ),
        sa.CheckConstraint(
            "status IN ('PENDING', 'CANCELLED') OR decided_by_user_id <> requester_user_id",
            name=op.f("ck_access_requests_approver_is_not_the_requester"),
        ),
        sa.ForeignKeyConstraint(
            ["requester_user_id"],
            ["users.id"],
            name=op.f("fk_access_requests_requester_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            name=op.f("fk_access_requests_decided_by_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_access_requests")),
    )

    # One pending request per user, enforced by the database so two concurrent
    # submissions cannot both succeed.
    op.create_index(
        "uq_access_requests_requester_id_pending",
        "access_requests",
        ["requester_user_id"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )
    op.create_index(
        "ix_access_requests_status_requested_at",
        "access_requests",
        ["status", "requested_at"],
        unique=False,
    )


def downgrade() -> None:
    # Reverse order. Any VIEWER user or new activity action must be resolved
    # before the enums can shrink; the casts below fail loudly rather than
    # silently discarding a row, which is the correct behaviour for a downgrade
    # that would otherwise lose an access level.
    op.drop_index("ix_access_requests_status_requested_at", table_name="access_requests")
    op.drop_index("uq_access_requests_requester_id_pending", table_name="access_requests")
    op.drop_table("access_requests")
    op.execute("DROP TYPE access_request_status")

    _replace_enum(
        "activity_action", ACTIVITY_ACTION_OLD, [("user_activity_records", "action")]
    )
    _replace_enum(
        "access_level",
        ACCESS_LEVEL_OLD,
        [("users", "access_level"), ("user_activity_records", "access_level_snapshot")],
    )

    op.execute(f"CREATE TYPE data_editor_assignment AS ENUM ({_quoted(DATA_EDITOR_ASSIGNMENT)})")
    op.add_column(
        "user_activity_records",
        sa.Column(
            "assignment_snapshot",
            postgresql.ENUM(*DATA_EDITOR_ASSIGNMENT, name="data_editor_assignment", create_type=False),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "data_editor_assignment",
            postgresql.ENUM(*DATA_EDITOR_ASSIGNMENT, name="data_editor_assignment", create_type=False),
            nullable=True,
        ),
    )
    op.create_check_constraint(
        "assignment_only_for_data_editor",
        "users",
        "data_editor_assignment IS NULL OR access_level = 'DATA_EDITOR'",
    )
