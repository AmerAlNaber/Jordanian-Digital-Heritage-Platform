"""Reader routes: sessions, heartbeat and the manifest (RDR-1, RDR-5, RDR-6, SEC-2, SEC-10)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import JSONResponse

from jdhp_api.core.authz import Authorize, Authorized
from jdhp_api.core.storage import ObjectStore
from jdhp_api.core.tasks import TaskDispatcher, get_dispatcher
from jdhp_api.modules.reader import printing, service
from jdhp_api.modules.reader.loaders import (
    load_print_job,
    load_session,
    load_session_for_print,
    load_work_for_manifest,
    load_work_for_open,
)
from jdhp_api.modules.reader.schemas import (
    Heartbeat,
    PrintJobOut,
    PrintLinkOut,
    PrintRequest,
    ReaderSessionOut,
    SessionOpen,
)
from jdhp_api.modules.reader.service import RequestFacts
from jdhp_api.modules.search.router import get_store

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


# --- Print (RDR-4, SEC-11, SEC-15) ------------------------------------------------------------


@router.post(
    "/sessions/{session}/print",
    response_model=PrintJobOut,
    status_code=status.HTTP_202_ACCEPTED,
)
async def request_print(
    request: Request,
    data: PrintRequest,
    authorized: Annotated[Authorized, Depends(Authorize("print", "work", load_session_for_print))],
    dispatcher: Annotated[TaskDispatcher, Depends(get_dispatcher)],
) -> PrintJobOut:
    """Ask for a watermarked, low-resolution PDF of pages within the session's grant. The
    caller presents both credentials, the signed-in token and the session's grant token; the
    request is logged with its page numbers and counted against the grant's quota."""
    return await printing.request_print(
        request.app.state.reader,
        context=authorized.resource,
        principal=authorized.principal,
        pages=data.pages,
        facts=_facts(request, authorized),
        dispatcher=dispatcher,
    )


@router.get("/prints/{job}", response_model=PrintJobOut)
async def get_print(
    request: Request,
    authorized: Annotated[Authorized, Depends(Authorize("view", "print_job", load_print_job))],
) -> PrintJobOut:
    return await printing.view_job(request.app.state.reader, authorized.resource)


@router.post("/prints/{job}/link", response_model=PrintLinkOut)
async def print_link(
    request: Request,
    authorized: Annotated[Authorized, Depends(Authorize("link", "print_job", load_print_job))],
) -> PrintLinkOut:
    """A single-use download link that expires in fifteen minutes (SEC-15)."""
    return await printing.mint_download_link(
        request.app.state.reader,
        job=authorized.resource,
        principal=authorized.principal,
        facts=_facts(request, authorized),
    )


@router.get("/prints/{job}/file")
async def print_file(
    request: Request,
    authorized: Annotated[Authorized, Depends(Authorize("download", "print_job", load_print_job))],
    store: Annotated[ObjectStore, Depends(get_store)],
) -> Response:
    """The PDF, once. The token in ``t`` is the credential; the file is deleted after this."""
    data, filename = await printing.deliver(
        request.app.state.reader,
        store,
        job=authorized.resource,
        principal=authorized.principal,
        facts=_facts(request, authorized),
    )
    return Response(
        content=data,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
