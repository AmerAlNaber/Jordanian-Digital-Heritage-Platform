"""Audit viewer routes (ADM-5, SEC-25): search by user, resource, action and time."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from jdhp_api.core import audit
from jdhp_api.core.authz import Authorize, Authorized
from jdhp_api.core.pagination import PageParams, Paginated, page_params
from jdhp_api.modules.audit.models import AuditEvent
from jdhp_api.modules.audit.schemas import AuditEventOut, ChainVerification

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events", response_model=Paginated[AuditEventOut])
async def list_events(
    authorized: Annotated[Authorized, Depends(Authorize("list", "audit_event"))],
    page: Annotated[PageParams, Depends(page_params)],
    actor: Annotated[str | None, Query(max_length=64)] = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
    resource_kind: Annotated[str | None, Query(max_length=32)] = None,
    resource_id: Annotated[str | None, Query(max_length=128)] = None,
    since: dt.datetime | None = None,
    until: dt.datetime | None = None,
) -> Paginated[AuditEventOut]:
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
    total = await authorized.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await authorized.session.scalars(
        stmt.order_by(AuditEvent.seq.desc()).limit(page.limit).offset(page.offset)
    )
    items = [AuditEventOut.model_validate(e, from_attributes=True) for e in rows.all()]
    return Paginated(items=items, total=int(total), limit=page.limit, offset=page.offset)


@router.get("/verify", response_model=ChainVerification)
async def verify(
    authorized: Annotated[Authorized, Depends(Authorize("verify", "audit_event"))],
) -> ChainVerification:
    intact, checked = await audit.verify_chain(authorized.session)
    return ChainVerification(intact=intact, events_checked=checked)
