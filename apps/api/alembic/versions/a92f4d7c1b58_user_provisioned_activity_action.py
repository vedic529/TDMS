"""USER_PROVISIONED activity action

A Super Admin granting someone access directly is not the same event as
`ROLE_CHANGED` — no role changed, an account came into existence with a level
already attached — and it is not a generic `CREATE`, which is what a course or a
unit record uses. Recording it as either would make the one action worth
auditing most closely the hardest to find.

The enum is **recreated** rather than extended with `ADD VALUE`. Postgres cannot
drop an enum label, so `ADD VALUE` is a one-way change; rename/create/cast/drop
leaves the downgrade able to do its job. Same approach as `805d65b129f2`.

Revision ID: a92f4d7c1b58
Revises: f3d81e6b0c47
"""

from __future__ import annotations

from alembic import op

revision = "a92f4d7c1b58"
down_revision = "f3d81e6b0c47"
branch_labels = None
depends_on = None

#: (table, column) pairs typed by the enum.
COLUMNS = [("user_activity_records", "action")]

BEFORE = [
    "SIGN_IN", "SIGN_OUT", "CREATE", "UPDATE", "DELETE", "RESTORE", "IMPORT",
    "EXPORT", "TIMETABLE_SAVE", "TIMETABLE_GENERATION", "CANCELLATION_AFTER_UPDATE",
    "OVERRIDE", "ACCESS_DENIED", "ACCESS_REQUEST_SUBMITTED", "ACCESS_REQUEST_APPROVED",
    "ACCESS_REQUEST_DENIED", "ACCESS_REQUEST_CANCELLED", "ROLE_CHANGED",
    "ACCOUNT_STATUS_CHANGED",
]
AFTER = BEFORE + ["USER_PROVISIONED"]


def _replace_enum(name: str, values: list[str]) -> None:
    quoted = ", ".join(f"'{value}'" for value in values)
    op.execute(f"ALTER TYPE {name} RENAME TO {name}_old")
    op.execute(f"CREATE TYPE {name} AS ENUM ({quoted})")
    for table, column in COLUMNS:
        op.execute(
            f"ALTER TABLE {table} ALTER COLUMN {column} "
            f"TYPE {name} USING {column}::text::{name}"
        )
    op.execute(f"DROP TYPE {name}_old")


def upgrade() -> None:
    _replace_enum("activity_action", AFTER)


def downgrade() -> None:
    # Rows recorded under the new label cannot be cast back, and rewriting them
    # to another action would falsify the audit trail. Refuse instead.
    from sqlalchemy import text

    stored = op.get_bind().execute(
        text("SELECT count(*) FROM user_activity_records WHERE action = 'USER_PROVISIONED'")
    ).scalar_one()
    if stored:
        raise RuntimeError(
            f"Cannot downgrade: {stored} activity record(s) use USER_PROVISIONED. "
            "Removing the label would mean relabelling audited events."
        )
    _replace_enum("activity_action", BEFORE)
