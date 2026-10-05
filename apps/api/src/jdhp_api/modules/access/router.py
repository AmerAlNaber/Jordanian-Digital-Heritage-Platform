"""Access routes: a member's own grants and the rights officer's revocation (ACS-2, SEC-5)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from jdhp_api.core.authz import Authorize, Authorized
from jdhp_api.modules.access import service
from jdhp_api.modules.access.loaders import load_grant
from jdhp_api.modules.access.schemas import GrantOut, GrantRevoke
from jdhp_api.modules.reader import service as reader_service

router = APIRouter(prefix="/access", tags=["access"])


@router.get("/grants", response_model=list[GrantOut])
async def list_own_grants(
    authorized: Annotated[Authorized, Depends(Authorize("list_own", "grant"))],
) -> list[GrantOut]:
    if authorized.principal.user_id is None:
        return []
    rows = await service.grants_for_user(authorized.session, authorized.principal.user_id)
    return [service.grant_out(grant, work) for grant, work in rows]


@router.post("/grants/{grant}/revoke", response_model=GrantOut)
async def revoke_grant(
    request: Request,
    data: GrantRevoke,
    authorized: Annotated[Authorized, Depends(Authorize("revoke", "grant", load_grant))],
) -> GrantOut:
    grant = authorized.resource
    work = await service.work_for_grant(authorized.session, grant)
    await service.revoke_grant(
        authorized.session,
        grant,
        actor=authorized.principal,
        reason=data.reason,
        request_id=authorized.request_id,
        work_public_id=work.public_id,
    )
    await reader_service.end_sessions_for_grant(
        request.app.state.reader, grant_id=grant.id, reason="revoked"
    )
    return service.grant_out(grant, work)
