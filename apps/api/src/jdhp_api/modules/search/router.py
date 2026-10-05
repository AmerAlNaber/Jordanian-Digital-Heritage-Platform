"""Search route. One route, one policy check, no text in the response (CAT-4)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response

from jdhp_api.core.authz import Authorize, Authorized
from jdhp_api.core.config import Settings
from jdhp_api.core.deps import current_settings
from jdhp_api.core.orm import AccessClass
from jdhp_api.core.storage import ObjectStore, app_store
from jdhp_api.modules.catalog.router import public_cache
from jdhp_api.modules.search import service
from jdhp_api.modules.search.backend import OpenSearchBackend, SearchBackend
from jdhp_api.modules.search.schemas import SearchResponse
from jdhp_api.modules.search.service import MAX_PAGES_PER_WORK, WORKS_FETCH, SearchRequest

router = APIRouter(tags=["search"])

NAME_PATTERN = r"^[a-z0-9]{1,32}$"
FACET_VALUE = Query(max_length=20)


def get_search_backend(request: Request) -> SearchBackend:
    backend = getattr(request.app.state, "search_backend", None)
    if backend is None:
        backend = OpenSearchBackend(request.app.state.settings)
        request.app.state.search_backend = backend
    return backend


def get_store(request: Request) -> ObjectStore:
    store = getattr(request.app.state, "store", None)
    if store is None:
        store = app_store(request.app.state.settings)
        request.app.state.store = store
    return store


@router.get("/search", response_model=SearchResponse)
async def search(
    response: Response,
    authorized: Annotated[Authorized, Depends(Authorize("search", "work"))],
    settings: Annotated[Settings, Depends(current_settings)],
    backend: Annotated[SearchBackend, Depends(get_search_backend)],
    store: Annotated[ObjectStore, Depends(get_store)],
    q: Annotated[str, Query(min_length=1, max_length=200, description="The query, in any script")],
    collection: Annotated[
        str | None,
        Query(pattern=NAME_PATTERN, description="Search within this collection's works"),
    ] = None,
    work: Annotated[
        str | None,
        Query(pattern=NAME_PATTERN, description="Search within one work; takes precedence"),
    ] = None,
    subject: Annotated[list[str], FACET_VALUE] = [],  # noqa: B006 - FastAPI query list default
    place: Annotated[list[str], FACET_VALUE] = [],  # noqa: B006
    period: Annotated[list[str], FACET_VALUE] = [],  # noqa: B006
    language: Annotated[list[str], FACET_VALUE] = [],  # noqa: B006
    access_class: Annotated[list[AccessClass], FACET_VALUE] = [],  # noqa: B006
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=WORKS_FETCH - 1)] = 0,
    pages_per_work: Annotated[int, Query(ge=0, le=MAX_PAGES_PER_WORK)] = 3,
) -> SearchResponse:
    """Unified search over works and page text. Page hits carry regions on the scan for
    pages the caller may see, and never the text itself (SRCH-1 to SRCH-4, CAT-4)."""
    request = SearchRequest(
        q=q.strip(),
        collection=collection,
        work=work,
        subjects=tuple(subject),
        places=tuple(place),
        periods=tuple(period),
        languages=tuple(language),
        access_classes=tuple(str(value) for value in access_class),
        limit=limit,
        offset=offset,
        pages_per_work=pages_per_work,
    )
    result = await service.search(
        authorized.session, authorized.principal, settings, backend, store, request
    )
    public_cache(response, authorized)
    return result
