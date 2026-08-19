"""Shared test fixtures.

Tests that write run against a **temporary PostgreSQL database** created,
migrated with Alembic, and dropped by the fixture below. `tdms_dev` is never
written to: several tests deliberately create wrong states — a conflicting role,
a demoted last Super Admin — which must not survive in a development database.

PostgreSQL, not SQLite. The behaviour under test is `citext` case-insensitivity,
native enum ordering, partial unique indexes and CHECK constraints, none of which
SQLite has. A passing SQLite test would prove nothing about the database that
actually runs.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

TEST_DB = "tdms_test"
API_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def test_database_url() -> str:
    """A migrated, empty database for the whole test session."""
    settings = get_settings()
    if not settings.migration_database_url:
        pytest.skip("database not configured")

    # Admin credentials: the harness creates, migrates, truncates and drops a
    # database, none of which the least-privilege runtime role may do.
    base = make_url(settings.migration_database_url)
    temp_url = base.set(database=TEST_DB)

    try:
        admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"database unreachable: {type(exc).__name__}")

    with admin.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))

    rendered = temp_url.render_as_string(hide_password=False)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-x", f"db_url={rendered}", "upgrade", "head"],
        cwd=API_DIR,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:  # pragma: no cover
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
        # Scrub the password before the failure message reaches a terminal or CI log.
        detail = result.stderr[-2000:]
        if base.password:
            detail = detail.replace(base.password, "***")
        pytest.fail(f"alembic upgrade head failed on {TEST_DB}:\n{detail}")

    try:
        yield rendered
    finally:
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{TEST_DB}" WITH (FORCE)'))
        admin.dispose()


@pytest.fixture(scope="session")
def test_engine(test_database_url):
    engine = create_engine(test_database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="session")
def test_factory(test_engine):
    return sessionmaker(bind=test_engine, autoflush=False, expire_on_commit=False)


def truncate_all(engine) -> None:
    """Empty every table that tests write to, resetting identity sequences."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE access_requests, user_activity_records, users "
                "RESTART IDENTITY CASCADE"
            )
        )


@pytest.fixture()
def session(test_factory, test_engine):
    """A clean session on the temporary database, emptied before each test."""
    truncate_all(test_engine)
    with test_factory() as s:
        yield s
        s.rollback()
