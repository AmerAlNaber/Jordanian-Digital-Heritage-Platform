"""Resource loaders for grants: public name in, grant and its policy attributes out."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core.auth import Principal
from jdhp_api.core.authz import ResourceRef
from jdhp_api.core.errors import InvalidIdentifierError, NotFoundError
from jdhp_api.core.ids import is_valid_name
from jdhp_api.modules.access import service
from jdhp_api.modules.access.models import Grant
from jdhp_api.modules.identity.models import User


async def load_grant(
    request: Request, session: AsyncSession, _principal: Principal
) -> tuple[Grant, ResourceRef]:
    public_id = str(request.path_params.get("grant", ""))
    if not is_valid_name(public_id):
        raise InvalidIdentifierError
    grant = await service.get_grant_by_public_id(session, public_id)
    if grant is None:
        raise NotFoundError
    owner = await session.get(User, grant.user_id) if grant.user_id else None
    attr = {
        "owner_id": owner.keycloak_sub if owner else "",
        "institution_id": str(grant.institution_id or ""),
        "state": "revoked" if grant.revoked else "active",
    }
    return grant, ResourceRef(kind="grant", id=grant.public_id, attr=attr)
