"""Request-scoped dependencies that need both the principal and the database."""

from __future__ import annotations

from collections.abc import AsyncIterator

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core.auth import Principal, get_principal
from jdhp_api.core.config import Settings
from jdhp_api.core.db import Database


def get_database(request: Request) -> Database:
    database = getattr(request.app.state, "database", None)
    if database is None:  # pragma: no cover - the lifespan always sets it
        msg = "database is not configured on the application"
        raise RuntimeError(msg)
    return database  # type: ignore[no-any-return]


async def get_session(
    database: Database = Depends(get_database),
    principal: Principal = Depends(get_principal),
) -> AsyncIterator[AsyncSession]:
    """One transaction per request, carrying the principal's row-level security context."""
    async with database.session(principal.rls_context()) as session:
        yield session


def current_settings(request: Request) -> Settings:
    """The settings the application was created with, not whatever the environment holds."""
    return request.app.state.settings  # type: ignore[no-any-return]
