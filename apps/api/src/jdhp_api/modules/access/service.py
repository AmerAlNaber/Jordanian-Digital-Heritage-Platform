"""Grants: the only thing that makes a protected work readable."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.modules.access.models import Grant


async def active_grant_for(
    session: AsyncSession, *, user_id: uuid.UUID | None, work_id: uuid.UUID
) -> Grant | None:
    """The caller's live grant for a work, if any. Institutional grants arrive in Phase 2."""
    if user_id is None:
        return None
    now = dt.datetime.now(dt.UTC)
    stmt = (
        select(Grant)
        .where(
            Grant.user_id == user_id,
            Grant.work_id == work_id,
            Grant.revoked.is_(False),
            Grant.starts_at <= now,
            Grant.ends_at > now,
        )
        .order_by(Grant.ends_at.desc())
        .limit(1)
    )
    return (await session.scalars(stmt)).first()


def grant_covers_page(grant: Grant | None, seq: int) -> bool:
    if grant is None:
        return False
    if grant.page_from is None or grant.page_to is None:
        return True
    return grant.page_from <= seq <= grant.page_to
