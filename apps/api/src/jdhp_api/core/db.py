"""Database access: async engine, sessions and the row-level security context (SEC-7).

Every transaction starts by publishing who is acting (``app.user_id``, ``app.roles``,
``app.institution_id``) through ``set_config`` with the transaction-local flag, so the
row-level security policies in the schema see the caller, never the connection role.
"""

from __future__ import annotations

import contextlib
import dataclasses
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool

ANONYMOUS_ROLE = "anonymous"
SYSTEM_ROLE = "system"


@dataclasses.dataclass(frozen=True, slots=True)
class RlsContext:
    """What the database learns about the caller for the duration of one transaction."""

    user_id: str
    roles: tuple[str, ...]
    institution_id: str

    @classmethod
    def anonymous(cls) -> RlsContext:
        return cls(user_id="", roles=(ANONYMOUS_ROLE,), institution_id="")

    @classmethod
    def system(cls) -> RlsContext:
        """Internal work with no human principal: identity sync, pipeline tasks, schedulers."""
        return cls(user_id="", roles=(SYSTEM_ROLE,), institution_id="")

    @property
    def roles_setting(self) -> str:
        return ",".join(self.roles)


async def apply_rls_context(session: AsyncSession, ctx: RlsContext) -> None:
    await session.execute(
        text(
            "SELECT set_config('app.user_id', :user_id, true),"
            " set_config('app.roles', :roles, true),"
            " set_config('app.institution_id', :institution_id, true)"
        ),
        {"user_id": ctx.user_id, "roles": ctx.roles_setting, "institution_id": ctx.institution_id},
    )


class Database:
    """One engine per process. Sessions are short-lived and always carry an RLS context."""

    def __init__(self, url: str, *, echo: bool = False, pooled: bool = True) -> None:
        kwargs: dict[str, Any] = {"echo": echo, "pool_pre_ping": True}
        if pooled:
            kwargs.update(pool_size=10, max_overflow=20)
        else:
            kwargs["poolclass"] = NullPool
        self.engine: AsyncEngine = create_async_engine(url, **kwargs)
        self._sessions = async_sessionmaker(
            self.engine, expire_on_commit=False, class_=AsyncSession
        )

    @contextlib.asynccontextmanager
    async def session(self, ctx: RlsContext) -> AsyncIterator[AsyncSession]:
        """One transaction: commits on success, rolls back on any exception."""
        async with self._sessions() as session, session.begin():
            await apply_rls_context(session, ctx)
            yield session

    async def ping(self) -> bool:
        async with self.engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            return bool(result.scalar_one() == 1)

    async def dispose(self) -> None:
        await self.engine.dispose()
