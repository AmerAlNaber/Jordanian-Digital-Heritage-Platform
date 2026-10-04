"""Catalog routes. Public reads are edge-cacheable for anonymous callers (PRF-4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from jdhp_api.core.authz import Authorize, Authorized
from jdhp_api.core.config import Settings
from jdhp_api.core.deps import current_settings
from jdhp_api.core.orm import AccessClass, TermScheme
from jdhp_api.core.pagination import PageParams, Paginated, page_params
from jdhp_api.modules.catalog import service
from jdhp_api.modules.catalog.loaders import load_by_name, load_collection, load_work
from jdhp_api.modules.catalog.models import Collection, Work
from jdhp_api.modules.catalog.schemas import (
    CollectionDetail,
    CollectionSummary,
    PageSummary,
    Resolution,
    TermSummary,
    WorkCreate,
    WorkDetail,
    WorkSummary,
    WorkUpdate,
)

router = APIRouter(tags=["catalog"])

PUBLIC_CACHE = "public, max-age=60, s-maxage=300"


def public_cache(response: Response, authorized: Authorized) -> None:
    if not authorized.principal.authenticated:
        response.headers["Cache-Control"] = PUBLIC_CACHE


@router.get("/works", response_model=Paginated[WorkSummary])
async def list_works(
    response: Response,
    authorized: Annotated[Authorized, Depends(Authorize("list", "work"))],
    settings: Annotated[Settings, Depends(current_settings)],
    page: Annotated[PageParams, Depends(page_params)],
    q: Annotated[str | None, Query(max_length=200)] = None,
    access_class: AccessClass | None = None,
) -> Paginated[WorkSummary]:
    items, total = await service.list_works(
        authorized.session,
        authorized.principal,
        settings,
        query=q,
        access_class=access_class,
        limit=page.limit,
        offset=page.offset,
    )
    public_cache(response, authorized)
    return Paginated(items=items, total=total, limit=page.limit, offset=page.offset)


@router.post("/works", response_model=WorkDetail, status_code=status.HTTP_201_CREATED)
async def create_work(
    data: WorkCreate,
    authorized: Annotated[Authorized, Depends(Authorize("create", "work"))],
    settings: Annotated[Settings, Depends(current_settings)],
) -> WorkDetail:
    work = await service.create_work(
        authorized.session, data, authorized.principal, settings, request_id=authorized.request_id
    )
    return await service.work_detail(
        authorized.session, work, authorized.principal, settings, can_read=False
    )


@router.get("/works/{name}", response_model=WorkDetail)
async def get_work(
    request: Request,
    response: Response,
    authorized: Annotated[
        Authorized, Depends(Authorize("view", "work", load_work, hide_existence=True))
    ],
    settings: Annotated[Settings, Depends(current_settings)],
) -> WorkDetail:
    work: Work = authorized.resource
    policy = request.app.state.policy_client
    can_read = await policy.is_allowed(
        authorized.principal, "read", authorized.ref, authorized.request_id
    )
    public_cache(response, authorized)
    return await service.work_detail(
        authorized.session, work, authorized.principal, settings, can_read=can_read
    )


@router.patch("/works/{name}", response_model=WorkDetail)
async def update_work(
    data: WorkUpdate,
    authorized: Annotated[
        Authorized, Depends(Authorize("edit", "work", load_work, hide_existence=True))
    ],
    settings: Annotated[Settings, Depends(current_settings)],
) -> WorkDetail:
    work = await service.update_work(
        authorized.session,
        authorized.resource,
        data,
        authorized.principal,
        request_id=authorized.request_id,
    )
    return await service.work_detail(
        authorized.session, work, authorized.principal, settings, can_read=False
    )


@router.get("/works/{name}/pages", response_model=list[PageSummary])
async def list_pages(
    response: Response,
    authorized: Annotated[
        Authorized, Depends(Authorize("view", "work", load_work, hide_existence=True))
    ],
    settings: Annotated[Settings, Depends(current_settings)],
) -> list[PageSummary]:
    public_cache(response, authorized)
    return await service.list_pages(authorized.session, authorized.resource, settings)


@router.get("/collections", response_model=Paginated[CollectionSummary])
async def list_collections(
    response: Response,
    authorized: Annotated[Authorized, Depends(Authorize("list", "collection"))],
    settings: Annotated[Settings, Depends(current_settings)],
    page: Annotated[PageParams, Depends(page_params)],
) -> Paginated[CollectionSummary]:
    items, total = await service.list_collections(
        authorized.session, authorized.principal, settings, limit=page.limit, offset=page.offset
    )
    public_cache(response, authorized)
    return Paginated(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/collections/{name}", response_model=CollectionDetail)
async def get_collection(
    response: Response,
    authorized: Annotated[
        Authorized, Depends(Authorize("view", "collection", load_collection, hide_existence=True))
    ],
    settings: Annotated[Settings, Depends(current_settings)],
) -> CollectionDetail:
    collection: Collection = authorized.resource
    public_cache(response, authorized)
    return await service.collection_detail(
        authorized.session, collection, authorized.principal, settings
    )


@router.get("/vocabulary/{scheme}", response_model=Paginated[TermSummary])
async def list_terms(
    scheme: TermScheme,
    response: Response,
    authorized: Annotated[Authorized, Depends(Authorize("list", "vocabulary_term"))],
    page: Annotated[PageParams, Depends(page_params)],
) -> Paginated[TermSummary]:
    items, total = await service.list_terms(
        authorized.session,
        authorized.principal,
        scheme=scheme,
        limit=page.limit,
        offset=page.offset,
    )
    public_cache(response, authorized)
    return Paginated(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/resolve/{name}", response_model=Resolution)
async def resolve(
    response: Response,
    authorized: Annotated[
        Authorized, Depends(Authorize("view", "work", load_by_name, hide_existence=True))
    ],
    settings: Annotated[Settings, Depends(current_settings)],
) -> Resolution:
    """Persistent identifier resolution (INT-7). The web app redirects to ``path``."""
    kind = authorized.ref.kind
    public_cache(response, authorized)
    path = f"/works/{authorized.ref.id}" if kind == "work" else f"/collections/{authorized.ref.id}"
    return Resolution(
        kind=kind,
        public_id=authorized.ref.id,
        ark=f"ark:/{settings.ark_naan}/{authorized.ref.id}",
        path=path,
    )
