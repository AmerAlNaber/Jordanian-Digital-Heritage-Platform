"""Alembic environment.

Runs against ``JDHP_MIGRATION_DATABASE_URL`` (the owner role) or, when a caller passes a
connection through ``config.attributes["connection"]``, against that connection. Tests use
the second path so migrations run inside their own harness.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from jdhp_api import models  # noqa: F401  # registers every table on the metadata
from jdhp_api.core.orm import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def database_url() -> str:
    url = (
        config.get_main_option("sqlalchemy.url")
        or os.environ.get("JDHP_MIGRATION_DATABASE_URL")
        or os.environ.get("JDHP_DATABASE_URL")
    )
    if not url:
        msg = "set JDHP_MIGRATION_DATABASE_URL or JDHP_DATABASE_URL"
        raise RuntimeError(msg)
    return url


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        {"sqlalchemy.url": database_url()}, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        do_run_migrations(connection)
    else:
        asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
