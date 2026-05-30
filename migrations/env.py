from __future__ import annotations

import asyncio
import os
import sys
from logging.config import fileConfig

# Ensure project root is on sys.path so 'app.*' imports resolve when
# alembic is invoked as a CLI command from /app.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.database import Base
from app.core.config import get_settings

# Import all models so their tables are registered on Base.metadata before
# autogenerate inspects it. The side-effect import is intentional.
import app.models  # noqa: F401

config = context.config
target_metadata = Base.metadata

if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _db_url() -> str:
    # Prefer the live app settings over the placeholder in alembic.ini so the
    # same .env that runs FastAPI also drives migrations.
    return get_settings().database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live DB connection."""
    context.configure(
        url=_db_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine = create_async_engine(_db_url(), pool_pre_ping=True)
    async with engine.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
