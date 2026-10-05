"""Content routes. The API refuses to return an unapproved AI object to non-staff (REV-1)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from jdhp_api.core.authz import Authorize, Authorized
from jdhp_api.core.config import Settings
from jdhp_api.core.deps import current_settings
from jdhp_api.core.orm import ProvenanceType
from jdhp_api.modules.catalog.loaders import load_work
from jdhp_api.modules.content import service
from jdhp_api.modules.content.loaders import load_content_object
from jdhp_api.modules.content.schemas import ContentObjectCreate, ContentObjectOut

router = APIRouter(tags=["content"])


@router.get("/works/{name}/content", response_model=list[ContentObjectOut])
async def list_content(
    authorized: Annotated[
        Authorized, Depends(Authorize("view", "work", load_work, hide_existence=True))
    ],
    settings: Annotated[Settings, Depends(current_settings)],
    page_seq: Annotated[int | None, Query(ge=1)] = None,
    provenance_type: ProvenanceType | None = None,
) -> list[ContentObjectOut]:
    objects = await service.list_for_work(
        authorized.session,
        authorized.resource,
        authorized.principal,
        page_seq=page_seq,
        provenance_type=provenance_type,
    )
    return await service.to_out(authorized.session, objects, authorized.resource, settings)


@router.post(
    "/works/{name}/content", response_model=ContentObjectOut, status_code=status.HTTP_201_CREATED
)
async def create_content(
    data: ContentObjectCreate,
    authorized: Annotated[Authorized, Depends(Authorize("create", "content_object"))],
    work_access: Annotated[
        Authorized, Depends(Authorize("view", "work", load_work, hide_existence=True))
    ],
    settings: Annotated[Settings, Depends(current_settings)],
) -> ContentObjectOut:
    obj = await service.create(
        authorized.session,
        work_access.resource,
        data,
        actor_id=authorized.principal.id,
        actor_roles=authorized.principal.roles,
        created_by=authorized.principal.user_id,
        request_id=authorized.request_id,
    )
    return (await service.to_out(authorized.session, [obj], work_access.resource, settings))[0]


@router.get("/content/{public_id}", response_model=ContentObjectOut)
async def get_content(
    authorized: Annotated[
        Authorized,
        Depends(Authorize("view", "content_object", load_content_object, hide_existence=True)),
    ],
    settings: Annotated[Settings, Depends(current_settings)],
) -> ContentObjectOut:
    obj, work = authorized.resource
    return (await service.to_out(authorized.session, [obj], work, settings))[0]
