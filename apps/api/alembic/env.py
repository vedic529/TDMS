"""Alembic environment for TDMS.

The database URL is taken from the application configuration at runtime, never
from `alembic.ini`, so no secret is committed.

`app.models` is imported for its side effect: it registers every model on
`Base.metadata`. Without that import, autogeneration would silently omit tables.
"""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Make `app` importable when Alembic is run from apps/api.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings  # noqa: E402
from app.models import Base  # noqa: E402  (imports every model module)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    """Resolve the URL, preferring an explicit `-x db_url=...` override.

    The override exists so the blank-database rebuild and downgrade tests can
    target a temporary database without editing any committed configuration.
    """
    override = context.get_x_argument(as_dictionary=True).get("db_url")
    if override:
        return override

    # The ADMIN url: migrations create and drop objects, which the runtime
    # application role deliberately cannot do.
    url = get_settings().migration_database_url
    if not url:
        raise RuntimeError(
            "No database URL configured. Set DATABASE_URL, or set the TDMS_POSTGRES_* "
            "variables in the repository .env file."
        )
    return url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and run migrations against the live database."""
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()

    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Detect column type and server-default drift, so `alembic check`
            # is meaningful rather than cosmetic.
            compare_type=True,
            compare_server_default=True,
            include_schemas=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
