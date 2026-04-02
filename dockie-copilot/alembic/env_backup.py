"""Alembic migration environment - async-compatible."""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.core.config import get_settings

# Load the ORM metadata so Alembic can autogenerate migrations.
from app.models.orm import Base  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")

# Alembic Config object
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Load both URLs explicitly so online migrations use asyncpg and offline mode
# still gets a sync URL when needed.
_async_db_url = os.environ.get("DATABASE_URL", "")
_sync_db_url = os.environ.get("SYNC_DATABASE_URL", "")
_sync_url = _sync_db_url or _async_db_url.replace("postgresql+asyncpg://", "postgresql://")
if _sync_url:
    config.set_main_option("sqlalchemy.url", _sync_url)

target_metadata = Base.metadata
config.attributes["knowledge_vector_backend"] = get_settings().knowledge_vector_backend

IGNORED_TABLES = {
    "alembic_version",
    "adk_internal_metadata",
    "app_states",
    "events",
    "sessions",
    "spatial_ref_sys",
    "user_states",
}


def include_object(object_, name, type_, reflected, compare_to):
    if type_ == "table" and name in IGNORED_TABLES:
        return False
    return True


def run_migrations_offline() -> None:
    """Run migrations in offline mode (no live DB connection needed)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    # Older local databases may have an alembic_version.version_num column that
    # is too short for our descriptive revision IDs. Widen it preemptively so
    # upgrades can proceed cleanly.
    connection.exec_driver_sql(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_name = 'alembic_version'
                  AND column_name = 'version_num'
            ) THEN
                ALTER TABLE alembic_version
                ALTER COLUMN version_num TYPE VARCHAR(128);
            END IF;
        END $$;
        """
    )
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations using an async engine (required for asyncpg)."""
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _async_db_url or cfg.get("sqlalchemy.url", "")

    connectable = async_engine_from_config(
        cfg,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    # Use an explicit transaction so Postgres DDL is committed instead of
    # being rolled back when the async connection closes.
    async with connectable.begin() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
