"""The least-privilege runtime database role (approved 11 August 2026).

These tests connect **as `tdms_app`** — the identity FastAPI actually uses — and
try to do things it must not be able to do. Everything else in the suite runs as
the administrator, so without this module the restrictions would never be
exercised.

The point of the role is LOG-05. "We never update activity records" is a
convention that a bug or an attacker can ignore; a role that *cannot* update them
is a control. Someone who reaches the application's database connection still
cannot erase what they did.
"""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ProgrammingError

from app.core.config import get_settings

pytestmark = pytest.mark.database

ADMIN_ROLE = "postgres"


@pytest.fixture(scope="module")
def app_engine():
    """An engine connected as the runtime role, against the development database."""
    settings = get_settings()
    if not settings.has_database:
        pytest.skip("database not configured")
    if not settings.uses_least_privilege_runtime_role:
        pytest.skip("the tdms_app role has not been created on this machine")

    engine = create_engine(settings.database_url)
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"cannot connect as the runtime role: {type(exc).__name__}")

    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture()
def app_connection(app_engine):
    """A connection whose transaction is always rolled back."""
    conn = app_engine.connect()
    trans = conn.begin()
    try:
        yield conn
    finally:
        trans.rollback()
        conn.close()


# ---------------------------------------------------------------------------
# Identity
# ---------------------------------------------------------------------------


def test_the_application_does_not_connect_as_the_administrator():
    settings = get_settings()
    assert settings.runtime_identity != ADMIN_ROLE
    assert settings.uses_least_privilege_runtime_role is True


def test_migrations_still_use_the_administrator():
    """Two separate identities, as approved."""
    settings = get_settings()
    admin_user = make_url(settings.migration_database_url).username
    assert admin_user == ADMIN_ROLE
    assert make_url(settings.database_url).username != admin_user


def test_the_runtime_role_is_not_a_superuser(app_connection):
    row = app_connection.execute(
        text(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
            "FROM pg_roles WHERE rolname = current_user"
        )
    ).one()
    assert row.rolsuper is False
    assert row.rolcreatedb is False
    assert row.rolcreaterole is False
    assert row.rolreplication is False
    assert row.rolbypassrls is False


# ---------------------------------------------------------------------------
# LOG-05 — the activity record is append-only, by privilege
# ---------------------------------------------------------------------------


def test_the_runtime_role_may_read_activity_records(app_connection):
    app_connection.execute(text("SELECT count(*) FROM user_activity_records"))


def test_the_runtime_role_may_append_an_activity_record(app_connection):
    app_connection.execute(
        text(
            "INSERT INTO user_activity_records "
            "(occurred_at, user_reference_snapshot, page_or_function, action, result, "
            " plain_language_detail) "
            "VALUES (:t, 'privilege test', 'Test', 'SIGN_IN', 'COMPLETED', 'append allowed')"
        ),
        {"t": dt.datetime.now(dt.timezone.utc)},
    )


def test_the_runtime_role_cannot_update_an_activity_record(app_connection):
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_connection.execute(
            text("UPDATE user_activity_records SET plain_language_detail = 'rewritten'")
        )


def test_the_runtime_role_cannot_delete_an_activity_record(app_connection):
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_connection.execute(text("DELETE FROM user_activity_records"))


def test_the_runtime_role_cannot_truncate_activity_records(app_connection):
    with pytest.raises(ProgrammingError):
        app_connection.execute(text("TRUNCATE user_activity_records"))


# ---------------------------------------------------------------------------
# The schema is not the application's to change
# ---------------------------------------------------------------------------


def test_the_runtime_role_cannot_create_a_table(app_connection):
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_connection.execute(text("CREATE TABLE privilege_probe (id integer)"))


def test_the_runtime_role_cannot_drop_a_table(app_connection):
    with pytest.raises(ProgrammingError, match="must be owner"):
        app_connection.execute(text("DROP TABLE student_groups"))


def test_the_runtime_role_cannot_alter_a_table(app_connection):
    with pytest.raises(ProgrammingError, match="must be owner"):
        app_connection.execute(text("ALTER TABLE students ADD COLUMN probe text"))


def test_the_runtime_role_cannot_write_the_alembic_version(app_connection):
    """Migration bookkeeping belongs to migrations, not to request handlers."""
    with pytest.raises(ProgrammingError, match="permission denied"):
        app_connection.execute(text("UPDATE alembic_version SET version_num = 'tampered'"))


# ---------------------------------------------------------------------------
# Normal business access still works
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "table",
    ["users", "access_requests", "students", "student_groups", "course_offerings", "trainers"],
)
def test_the_runtime_role_may_read_business_tables(app_connection, table):
    app_connection.execute(text(f"SELECT count(*) FROM {table}"))


def test_the_runtime_role_may_write_a_business_table(app_connection):
    """Rolled back — this only proves the privilege exists."""
    app_connection.execute(
        text(
            "INSERT INTO colleges (college_short_name, college_full_name) "
            "VALUES ('PRIV', 'Privilege probe')"
        )
    )
    app_connection.execute(
        text("UPDATE colleges SET college_full_name = 'updated' WHERE college_short_name = 'PRIV'")
    )
    app_connection.execute(text("DELETE FROM colleges WHERE college_short_name = 'PRIV'"))
