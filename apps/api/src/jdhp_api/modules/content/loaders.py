"""Loaders for content objects: by public identifier, with the attributes the policy reads."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core.auth import Principal
from jdhp_api.core.authz import ResourceRef
from jdhp_api.core.errors import InvalidIdentifierError, NotFoundError
from jdhp_api.core.ids import is_valid_name
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.content import service
from jdhp_api.modules.content.models import ContentObject


async def load_content_object(
    request: Request, session: AsyncSession, _principal: Principal
) -> tuple[tuple[ContentObject, Work], ResourceRef]:
    public_id = str(request.path_params.get("public_id", ""))
    if not is_valid_name(public_id):
        raise InvalidIdentifierError
    obj = await service.get_by_public_id(session, public_id)
    if obj is None:
        raise NotFoundError
    work = await session.get(Work, obj.work_id)
    if work is None:
        raise NotFoundError
    return (obj, work), ResourceRef(
        kind="content_object", id=obj.public_id, attr=service.attributes(obj, work)
    )
