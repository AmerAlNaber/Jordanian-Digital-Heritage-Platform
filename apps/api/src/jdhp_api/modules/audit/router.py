"""Audit viewer routes (ADM-5, SEC-25): search by user, resource, action and time."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from jdhp_api.core import audit
from jdhp_api.core.authz import Authorize, Authorized
from jdhp_api.core.pagination import PageParams, Paginated, page_params
from jdhp_api.modules.audit import service
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
    events, total = await service.list_events(
        authorized.session,
        actor=actor,
        action=action,
        resource_kind=resource_kind,
        resource_id=resource_id,
        since=since,
        until=until,
        limit=page.limit,
        offset=page.offset,
    )
    items = [AuditEventOut.model_validate(e, from_attributes=True) for e in events]
    return Paginated(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/verify", response_model=ChainVerification)
async def verify(
    authorized: Annotated[Authorized, Depends(Authorize("verify", "audit_event"))],
) -> ChainVerification:
    intact, checked = await audit.verify_chain(authorized.session)
    return ChainVerification(intact=intact, events_checked=checked)
