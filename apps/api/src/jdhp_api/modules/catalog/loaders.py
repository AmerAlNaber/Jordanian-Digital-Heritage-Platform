"""Resource loaders for the policy engine: public identifier in, object and attributes out."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core.auth import Principal
from jdhp_api.core.authz import ResourceRef
from jdhp_api.core.errors import InvalidIdentifierError, NotFoundError
from jdhp_api.core.ids import is_valid_name
from jdhp_api.core.orm import PublishState
from jdhp_api.modules.access.service import active_grant_for
from jdhp_api.modules.catalog import service
from jdhp_api.modules.catalog.models import Collection, Work


def name_param(request: Request, key: str = "name") -> str:
    name = str(request.path_params.get(key, ""))
    if not is_valid_name(name):
        raise InvalidIdentifierError
    return name


async def load_work(
    request: Request, session: AsyncSession, principal: Principal
) -> tuple[Work, ResourceRef]:
    name = name_param(request)
    work = await service.get_work_by_name(session, name)
    if work is None:
        raise NotFoundError
    grant = await active_grant_for(session, user_id=principal.user_id, work_id=work.id)
    request.state.grant = grant
    return work, ResourceRef(
        kind="work", id=work.public_id, attr=service.work_attributes(work, grant)
    )


async def load_collection(
    request: Request, session: AsyncSession, _principal: Principal
) -> tuple[Collection, ResourceRef]:
    name = name_param(request)
    collection = await service.get_collection_by_name(session, name)
    if collection is None:
        raise NotFoundError
    attr: dict[str, Any] = {
        "access_class": "open",
        "publish_state": str(collection.publish_state),
        "frozen": False,
    }
    return collection, ResourceRef(kind="collection", id=collection.public_id, attr=attr)


async def load_by_name(
    request: Request, session: AsyncSession, principal: Principal
) -> tuple[Any, ResourceRef]:
    """The persistent identifier resolver: the shoulder decides the kind."""
    name = name_param(request)
    settings = request.app.state.settings
    if name.startswith(settings.ark_shoulder_collection):
        return await load_collection(request, session, principal)
    if name.startswith(settings.ark_shoulder_work):
        return await load_work(request, session, principal)
    raise NotFoundError


def is_published(obj: Work | Collection) -> bool:
    return obj.publish_state == PublishState.PUBLISHED
