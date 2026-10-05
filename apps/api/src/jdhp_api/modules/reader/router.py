"""Reader routes: sessions, heartbeat and the manifest (RDR-1, RDR-5, RDR-6, SEC-2, SEC-10)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from jdhp_api.core.authz import Authorize, Authorized
from jdhp_api.modules.reader import service
from jdhp_api.modules.reader.loaders import load_session, load_work_for_manifest, load_work_for_open
from jdhp_api.modules.reader.schemas import Heartbeat, ReaderSessionOut, SessionOpen
from jdhp_api.modules.reader.service import RequestFacts

router = APIRouter(prefix="/reader", tags=["reader"])


def _facts(request: Request, authorized: Authorized) -> RequestFacts:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip()[:45] if forwarded else None
    if ip is None and request.client:
        ip = request.client.host
    return RequestFacts(
        request_id=authorized.request_id, ip=ip, user_agent=request.headers.get("user-agent")
    )


@router.post("/sessions", response_model=ReaderSessionOut, status_code=status.HTTP_201_CREATED)
async def open_session(
    request: Request,
    data: SessionOpen,
    authorized: Annotated[
        Authorized, Depends(Authorize("read", "work", load_work_for_open, hide_existence=True))
    ],
) -> ReaderSessionOut:
    return await service.open_session(
        request.app.state.reader,
        principal=authorized.principal,
        work=authorized.resource,
        grant=getattr(request.state, "grant", None),
        device_fingerprint=data.device_fingerprint,
        facts=_facts(request, authorized),
    )


@router.get("/sessions/{session}", response_model=ReaderSessionOut)
async def get_session(
    request: Request,
    authorized: Annotated[Authorized, Depends(Authorize("view", "reader_session", load_session))],
) -> ReaderSessionOut:
    return await service.session_view(request.app.state.reader, authorized.resource)


@router.post("/sessions/{session}/heartbeat", response_model=ReaderSessionOut)
async def heartbeat(
    request: Request,
    data: Heartbeat,
    authorized: Annotated[
        Authorized, Depends(Authorize("heartbeat", "reader_session", load_session))
    ],
) -> ReaderSessionOut:
    claims = request.state.grant_claims
    return await service.heartbeat(
        request.app.state.reader,
        reader=authorized.resource,
        claims=claims,
        principal=authorized.principal,
        device_fingerprint=data.device_fingerprint,
        pages_viewed=data.pages_viewed,
        dwell_seconds=data.dwell_seconds,
        facts=_facts(request, authorized),
    )


@router.delete("/sessions/{session}", status_code=status.HTTP_204_NO_CONTENT)
async def end_session(
    request: Request,
    authorized: Annotated[Authorized, Depends(Authorize("end", "reader_session", load_session))],
) -> Response:
    await service.end_session(
        request.app.state.reader,
        reader=authorized.resource,
        principal=authorized.principal,
        facts=_facts(request, authorized),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/works/{name}/manifest")
async def work_manifest(
    request: Request,
    authorized: Annotated[
        Authorized, Depends(Authorize("view", "work", load_work_for_manifest, hide_existence=True))
    ],
) -> JSONResponse:
    settings = request.app.state.settings
    work = authorized.resource
    pages = await service.pages_for_manifest(
        authorized.session, work, full=bool(getattr(request.state, "manifest_full", False))
    )
    body = service.manifest(settings, work, pages)
    return JSONResponse(
        body,
        media_type=service.MANIFEST_MEDIA_TYPE,
        headers={"Cache-Control": "private, no-store"},
    )
