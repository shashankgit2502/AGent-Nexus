"""Alembic environment — async SQLAlchemy 2.0 pattern.

Key design decisions (TECHNICAL §11.8):
  - Uses the async engine for migrations via run_sync.
  - Excludes framework-managed tables from autogenerate to prevent Alembic
    from trying to drop LangGraph checkpointer/store and PGVector tables.
"""

import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import create_async_engine

# Importing the models package registers every table on Base.metadata so
# Alembic's autogenerate / metadata target sees the full §11 schema (Step 9).
import app.db.models  # noqa: F401
from alembic import context

# Import Base so Alembic can see our ORM models for autogenerate
from app.core.config import get_settings
from app.db.alembic_filters import include_object
from app.db.base import Base

config = context.config
settings = get_settings()

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# Framework-managed table exclusion (TECHNICAL §11.8) — extracted so it is
# unit-testable (see app/db/alembic_filters.py + tests/db/test_alembic_filters.py).


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection (--sql flag)."""
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        include_object=include_object,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations via an async engine (required for asyncpg driver)."""
    connectable = create_async_engine(
        settings.DATABASE_URL,
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
