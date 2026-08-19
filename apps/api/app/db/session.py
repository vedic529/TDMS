"""SQLAlchemy engine and session factory.

Synchronous SQLAlchemy: the approved backend architecture does not call for
async, and async database plumbing would add complexity without a requirement.

Nothing here logs the database URL — it contains the password.
"""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


class DatabaseNotConfiguredError(RuntimeError):
    """Raised when no database URL is available."""


def get_engine() -> Engine:
    """Return the process-wide engine, creating it on first use."""
    global _engine
    if _engine is None:
        settings = get_settings()
        if not settings.has_database:
            raise DatabaseNotConfiguredError(
                "No database URL is configured. Set DATABASE_URL, or set the "
                "TDMS_POSTGRES_* variables in the repository .env file."
            )
        _engine = create_engine(
            settings.database_url,
            # Verify a pooled connection before handing it out, so a connection
            # dropped by a container restart surfaces as a retry, not an error.
            pool_pre_ping=True,
            # echo stays off: SQL logging would print parameter values.
            echo=False,
            future=True,
        )
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the process-wide session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), autoflush=False, expire_on_commit=False)
    return _session_factory


def get_session() -> Iterator[Session]:
    """Yield a session and always close it.

    Shaped as a generator so it can be used directly as a FastAPI dependency in
    a later step. No route uses it yet.
    """
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


def reset_engine() -> None:
    """Dispose of the engine and clear the cached factory. Used by tests."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
