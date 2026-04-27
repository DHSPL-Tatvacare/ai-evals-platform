"""Alembic environment for ai-evals-platform.

- Async-only: the app uses asyncpg via SQLAlchemy's async engine, so
  Alembic also runs against the same engine to avoid a parallel sync driver.
- DATABASE_URL is read from app.config.settings, never from alembic.ini.
- target_metadata = Base.metadata so `alembic revision --autogenerate`
  diffs the same model tree the app boots with.
"""
from __future__ import annotations

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.config import settings
from app.models import Base  # app/models/__init__.py side-effect-loads every model module

# alembic.ini points at this env.py; pull its [loggers] section into stdlib logging.
config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Inject the runtime DB URL after the file is parsed so secrets never live in alembic.ini.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate SQL without connecting (`alembic upgrade --sql`).

    Output goes to stdout; useful for review before applying via psql.
    """
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Sync helper invoked from inside `connection.run_sync(...)`."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
        # Keep autogenerate's diff sensitive enough to catch real drift but
        # quiet about cosmetic differences. Tune in Phase 7 as needed.
        include_schemas=False,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Connect via asyncpg and run migrations inside a transaction."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
