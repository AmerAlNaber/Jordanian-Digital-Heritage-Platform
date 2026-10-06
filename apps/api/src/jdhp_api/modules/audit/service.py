"""Audit viewer queries (ADM-5). Reads only; the writer lives in ``core.audit``."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.modules.audit.models import AuditEvent


def _filtered(
    *,
    actor: str | None,
    action: str | None,
    resource_kind: str | None,
    resource_id: str | None,
    since: dt.datetime | None,
    until: dt.datetime | None,
) -> Select[tuple[AuditEvent]]:
    stmt = select(AuditEvent)
    if actor:
        stmt = stmt.where(AuditEvent.actor_id == actor)
    if action:
        stmt = stmt.where(AuditEvent.action == action)
    if resource_kind:
        stmt = stmt.where(AuditEvent.resource_kind == resource_kind)
    if resource_id:
        stmt = stmt.where(AuditEvent.resource_id == resource_id)
    if since:
        stmt = stmt.where(AuditEvent.occurred_at >= since)
    if until:
        stmt = stmt.where(AuditEvent.occurred_at < until)
    return stmt


async def list_events(
    session: AsyncSession,
    *,
    actor: str | None,
    action: str | None,
    resource_kind: str | None,
    resource_id: str | None,
    since: dt.datetime | None,
    until: dt.datetime | None,
    limit: int,
    offset: int,
) -> tuple[Sequence[AuditEvent], int]:
    stmt = _filtered(
        actor=actor,
        action=action,
        resource_kind=resource_kind,
        resource_id=resource_id,
        since=since,
        until=until,
    )
    total = await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await session.scalars(stmt.order_by(AuditEvent.seq.desc()).limit(limit).offset(offset))
    return rows.all(), int(total)


async def events_for_export(
    session: AsyncSession,
    *,
    actor: str | None,
    action: str | None,
    resource_kind: str | None,
    resource_id: str | None,
    since: dt.datetime | None,
    until: dt.datetime | None,
    max_rows: int,
) -> tuple[Sequence[AuditEvent], int]:
    """Every matching event in chain order, or an empty list with the total when too many."""
    stmt = _filtered(
        actor=actor,
        action=action,
        resource_kind=resource_kind,
        resource_id=resource_id,
        since=since,
        until=until,
    )
    total = int(await session.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    if total > max_rows:
        return [], total
    rows = await session.scalars(stmt.order_by(AuditEvent.seq.asc()))
    return rows.all(), total
