"""Grants: the only thing that makes a protected work readable (ACS-2).

Phase 1 covers the Open and Registered classes: a signed-in member who opens such a work
receives a grant implied by the class (``GrantSource.ACCESS_CLASS``), which carries the
device limit and the print quota. Requests, payments and institutional licenses create
grants in Phase 2 through the same model.
"""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core import audit
from jdhp_api.core.auth import Principal
from jdhp_api.core.config import Settings
from jdhp_api.core.orm import AccessClass, AuditOutcome, AuditSeverity, GrantSource
from jdhp_api.modules.access.models import Grant
from jdhp_api.modules.access.schemas import GrantOut
from jdhp_api.modules.catalog.models import Work

CLASS_GRANT_CLASSES = frozenset({AccessClass.OPEN, AccessClass.REGISTERED})


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def is_active(grant: Grant, now: dt.datetime | None = None) -> bool:
    now = now or utcnow()
    return not grant.revoked and grant.starts_at <= now < grant.ends_at


async def active_grant_for(
    session: AsyncSession, *, user_id: uuid.UUID | None, work_id: uuid.UUID
) -> Grant | None:
    """The caller's live grant for a work, if any. Institutional grants arrive in Phase 2."""
    if user_id is None:
        return None
    now = utcnow()
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


async def ensure_class_grant(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    work: Work,
    settings: Settings,
    now: dt.datetime | None = None,
) -> Grant:
    """The grant a signed-in member holds on an Open or Registered work, created on first use."""
    if work.access_class not in CLASS_GRANT_CLASSES:
        msg = f"no class grant for access class {work.access_class}"
        raise ValueError(msg)
    existing = await active_grant_for(session, user_id=user_id, work_id=work.id)
    if existing is not None:
        return existing
    now = now or utcnow()
    grant = Grant(
        user_id=user_id,
        work_id=work.id,
        starts_at=now,
        ends_at=now + dt.timedelta(days=settings.registered_grant_days),
        device_limit=settings.default_device_limit,
        source=GrantSource.ACCESS_CLASS,
        print_quota=settings.print_quota_default_pages,
        created_by=user_id,
    )
    session.add(grant)
    await session.flush()
    return grant


async def get_grant_by_public_id(session: AsyncSession, public_id: str) -> Grant | None:
    return (await session.scalars(select(Grant).where(Grant.public_id == public_id))).first()


async def grants_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[tuple[Grant, Work]]:
    stmt = (
        select(Grant, Work)
        .join(Work, Work.id == Grant.work_id)
        .where(Grant.user_id == user_id)
        .order_by(Grant.ends_at.desc())
    )
    return [(row[0], row[1]) for row in (await session.execute(stmt)).all()]


async def work_for_grant(session: AsyncSession, grant: Grant) -> Work:
    work = await session.get(Work, grant.work_id)
    if work is None:  # pragma: no cover - a grant always references a work
        msg = "grant without a work"
        raise RuntimeError(msg)
    return work


async def revoke_grant(
    session: AsyncSession,
    grant: Grant,
    *,
    actor: Principal,
    reason: str,
    request_id: str | None,
    work_public_id: str,
) -> Grant:
    """Revoke a grant. Reader sessions on it are ended by the reader service (SEC-5)."""
    if not grant.revoked:
        grant.revoked = True
        grant.revoked_at = utcnow()
        grant.revoked_by = actor.user_id
        grant.revoke_reason = reason
        await session.flush()
    await audit.write(
        session,
        actor_id=actor.id,
        actor_type="user",
        actor_roles=actor.roles,
        action="grant.revoke",
        resource_kind="grant",
        resource_id=grant.public_id,
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.NOTICE,
        details={"work": work_public_id, "reason": reason},
        request_id=request_id,
    )
    return grant


def grant_out(grant: Grant, work: Work, now: dt.datetime | None = None) -> GrantOut:
    return GrantOut(
        public_id=grant.public_id,
        work=work.public_id,
        work_access_class=work.access_class,
        source=grant.source,
        starts_at=grant.starts_at,
        ends_at=grant.ends_at,
        device_limit=grant.device_limit,
        page_from=grant.page_from,
        page_to=grant.page_to,
        print_quota=grant.print_quota,
        print_used=grant.print_used,
        revoked=grant.revoked,
        revoked_at=grant.revoked_at,
        active=is_active(grant, now),
    )
