"""Resource loaders for the reader: the grant token is the credential on reader endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core.auth import Principal
from jdhp_api.core.authz import ResourceRef
from jdhp_api.core.db import RlsContext
from jdhp_api.core.errors import GrantTokenError, InvalidIdentifierError, NotFoundError
from jdhp_api.core.ids import is_valid_name
from jdhp_api.core.orm import ReaderSessionState
from jdhp_api.core.tokens import GrantClaims
from jdhp_api.modules.access.service import active_grant_for
from jdhp_api.modules.catalog import service as catalog_service
from jdhp_api.modules.catalog.loaders import load_work
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.identity.models import User
from jdhp_api.modules.reader import service
from jdhp_api.modules.reader.models import ReaderSession

GRANT_HEADER = "X-Jdhp-Grant"


def grant_claims_from(request: Request) -> GrantClaims | None:
    """Verify the grant token header when present. Invalid tokens are refused outright."""
    token = request.headers.get(GRANT_HEADER)
    if not token:
        return None
    issuer = request.app.state.reader.grant_tokens
    claims: GrantClaims = issuer.verify(token)
    return claims


async def load_work_for_open(
    request: Request, session: AsyncSession, principal: Principal
) -> tuple[Work, ResourceRef]:
    """The work named in the request body, with the caller's grant for the ``read`` decision."""
    body = await request.json()
    name = body.get("work") if isinstance(body, dict) else None
    if not isinstance(name, str) or not is_valid_name(name):
        raise InvalidIdentifierError
    work = await catalog_service.get_work_by_name(session, name)
    if work is None:
        raise NotFoundError
    grant = await active_grant_for(session, user_id=principal.user_id, work_id=work.id)
    request.state.grant = grant
    return work, ResourceRef(
        kind="work", id=work.public_id, attr=catalog_service.work_attributes(work, grant)
    )


async def load_work_for_manifest(
    request: Request, session: AsyncSession, principal: Principal
) -> tuple[Work, ResourceRef]:
    """The work from the path; a valid grant token for an active session unlocks every page."""
    work, ref = await load_work(request, session, principal)
    claims = grant_claims_from(request)
    full = False
    if claims is not None and claims.work_public_id == work.public_id:
        services = request.app.state.reader
        async with services.database.session(RlsContext.system()) as system:
            reader = await service.get_session_by_public_id(system, claims.session_id)
            full = reader is not None and reader.state == ReaderSessionState.ACTIVE
    request.state.manifest_full = full
    return work, ref


async def load_session(
    request: Request, _session: AsyncSession, principal: Principal
) -> tuple[ReaderSession, ResourceRef]:
    """A reader session by public name. The token proves possession; staff act by role.

    Rows are read under the system context: the caller's own context is anonymous on
    reader endpoints, and the verified token is what entitles it to this one session.
    """
    public_id = str(request.path_params.get("session", ""))
    if not is_valid_name(public_id):
        raise InvalidIdentifierError
    claims = grant_claims_from(request)
    if claims is None and not principal.is_staff:
        raise GrantTokenError
    services = request.app.state.reader
    async with services.database.session(RlsContext.system()) as system:
        reader = await service.get_session_by_public_id(system, public_id)
        if reader is None:
            raise NotFoundError
        owner = await system.get(User, reader.user_id) if reader.user_id else None
    token_valid = (
        claims is not None
        and claims.session_id == reader.public_id
        and claims.device_hash == reader.device_hash
        and (not principal.authenticated or claims.subject == principal.id)
    )
    request.state.grant_claims = claims if token_valid else None
    attr: dict[str, Any] = {
        "owner_id": owner.keycloak_sub if owner else "",
        "token_valid": token_valid,
        "state": str(reader.state),
    }
    return reader, ResourceRef(kind="reader_session", id=reader.public_id, attr=attr)
