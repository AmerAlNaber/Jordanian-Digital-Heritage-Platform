"""A migrated template database per session and a fresh clone per test, as the app role."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy import create_engine

API_DIR = Path(__file__).resolve().parents[3]
ADMIN_URL = os.environ.get(
    "JDHP_TEST_ADMIN_DATABASE_URL", "postgresql://postgres@localhost:54329/postgres"
)
APP_ROLE = "jdhp_app"
WORKER_ROLE = "jdhp_worker"
TEST_PASSWORD = "jdhp_test_password"  # noqa: S105 - local test cluster only


def admin_conn(dbname: str | None = None) -> psycopg.Connection[Any]:
    url = ADMIN_URL if dbname is None else ADMIN_URL.rsplit("/", 1)[0] + f"/{dbname}"
    return psycopg.connect(url, autocommit=True)


def admin_host_port() -> tuple[str, str]:
    rest = ADMIN_URL.split("@")[-1].split("/")[0]
    host, _, port = rest.partition(":")
    return host, port or "5432"


def ensure_roles() -> None:
    with admin_conn() as conn:
        for role in (APP_ROLE, WORKER_ROLE):
            exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)).fetchone()
            verb = "ALTER" if exists else "CREATE"
            conn.execute(
                sql.SQL("{verb} ROLE {role} LOGIN PASSWORD {password} NOBYPASSRLS").format(
                    verb=sql.SQL(verb),
                    role=sql.Identifier(role),
                    password=sql.Literal(TEST_PASSWORD),
                )
            )


def create_template() -> Iterator[str]:
    """Create roles, a database with pgvector, run migrations; yield the name; drop it after."""
    name = f"jdhp_tmpl_{uuid.uuid4().hex[:10]}"
    ensure_roles()
    with admin_conn() as conn:
        conn.execute(f'CREATE DATABASE "{name}"')
    with admin_conn(name) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
    sync_url = (
        ADMIN_URL.replace("postgresql://", "postgresql+psycopg://").rsplit("/", 1)[0] + f"/{name}"
    )
    engine = create_engine(sync_url)
    config = Config(str(API_DIR / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    engine.dispose()
    try:
        yield name
    finally:
        with admin_conn() as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def clone_database(template: str) -> Iterator[str]:
    name = f"jdhp_test_{uuid.uuid4().hex[:10]}"
    with admin_conn() as conn:
        conn.execute(f'CREATE DATABASE "{name}" TEMPLATE "{template}"')
    try:
        yield name
    finally:
        with admin_conn() as conn:
            conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def role_url(dbname: str, role: str) -> str:
    host, port = admin_host_port()
    return f"postgresql+asyncpg://{role}:{TEST_PASSWORD}@{host}:{port}/{dbname}"


def admin_async_url(dbname: str) -> str:
    return (
        ADMIN_URL.replace("postgresql://", "postgresql+asyncpg://").rsplit("/", 1)[0] + f"/{dbname}"
    )
