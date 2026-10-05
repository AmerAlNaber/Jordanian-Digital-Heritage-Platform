"""Print: a server-rendered, watermarked, low-resolution PDF (RDR-4, SEC-11, SEC-15).

A member with a reader session asks for pages. The request is checked against the grant's
page range and print quota and logged with the page numbers. A worker renders each page from
the access derivative at the print resolution, applies the reader's visible mark (user, grant,
work, time) and the session's forensic mark, wraps the JPEGs in a PDF and stores it in the
exports bucket. The owner then mints a download link: a random token whose hash is stored,
valid for fifteen minutes and for one download. The file is deleted once delivered.

Quota: a grant's used pages are the pages of every job that is not failed, so a render
failure gives the pages back without anyone touching the grant row.
"""

from __future__ import annotations

import asyncio
import dataclasses
import datetime as dt
import hashlib
import secrets
import uuid
from collections.abc import Sequence
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core import audit
from jdhp_api.core.auth import Principal
from jdhp_api.core.config import Settings
from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.errors import (
    ForbiddenError,
    GrantRequiredError,
    PrintNotReadyError,
    PrintPagesError,
    PrintQuotaError,
    ReaderSessionEndedError,
)
from jdhp_api.core.orm import AuditOutcome, AuditSeverity, PrintJobState
from jdhp_api.core.storage import ObjectStore
from jdhp_api.core.tasks import TaskDispatcher
from jdhp_api.core.tokens import ForensicKeys
from jdhp_api.modules.access.models import Grant
from jdhp_api.modules.access.service import grant_covers_page
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.identity.models import User
from jdhp_api.modules.ingest.models import Page
from jdhp_api.modules.reader.models import PrintJob, ReaderSession
from jdhp_api.modules.reader.pdf import PdfImage, build_pdf
from jdhp_api.modules.reader.schemas import PrintJobOut, PrintLinkOut
from jdhp_api.modules.reader.service import ReaderServices, RequestFacts, ending_reason, utcnow

if TYPE_CHECKING:
    from jdhp_api.modules.reader.images import ImageSource

RENDER_TASK = "jdhp.print.render"
QUOTA_STATES = (PrintJobState.QUEUED, PrintJobState.READY, PrintJobState.DOWNLOADED)
JPEG_QUALITY = 75
PRINT_PREFIX = "prints"
TOKEN_BYTES = 32
USER_TAG_LENGTH = 8
PRODUCER = "Jordanian Digital Heritage Platform"


@dataclasses.dataclass(frozen=True, slots=True)
class PrintContext:
    """What the print route's loader hands the service: the session and what it is bound to."""

    reader: ReaderSession
    work: Work
    grant: Grant
    user: User | None


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def user_tag(subject: str | None) -> str:
    return subject[:USER_TAG_LENGTH] if subject else "visitor"


def export_key(job_public_id: str) -> str:
    return f"{PRINT_PREFIX}/{job_public_id}.pdf"


# --- Quota ------------------------------------------------------------------------------------


async def pages_used(session: AsyncSession, grant_id: uuid.UUID) -> int:
    """Pages of every job on the grant that is queued, ready or downloaded."""
    stmt = select(func.coalesce(func.sum(func.cardinality(PrintJob.pages)), 0)).where(
        PrintJob.grant_id == grant_id, PrintJob.state.in_(QUOTA_STATES)
    )
    return int(await session.scalar(stmt) or 0)


async def quota_remaining(session: AsyncSession, grant: Grant) -> int:
    return max(0, grant.print_quota - await pages_used(session, grant.id))


def validate_pages(pages: Sequence[int], *, page_count: int, grant: Grant) -> list[int]:
    wanted = sorted(set(pages))
    if not wanted or wanted[0] < 1 or wanted[-1] > page_count:
        raise PrintPagesError
    if any(not grant_covers_page(grant, seq) for seq in wanted):
        raise PrintPagesError
    return wanted


def job_out(
    job: PrintJob, work_public_id: str, grant_public_id: str, remaining: int
) -> PrintJobOut:
    return PrintJobOut(
        public_id=job.public_id,
        work=work_public_id,
        grant=grant_public_id,
        state=job.state,
        pages=list(job.pages),
        quota_remaining=remaining,
        created_at=job.created_at,
        rendered_at=job.rendered_at,
        downloaded_at=job.downloaded_at,
    )


# --- Requesting -------------------------------------------------------------------------------


async def request_print(
    services: ReaderServices,
    *,
    context: PrintContext,
    principal: Principal,
    pages: Sequence[int],
    facts: RequestFacts,
    dispatcher: TaskDispatcher,
) -> PrintJobOut:
    """Record the request, reserve the pages against the quota and hand the render to a worker."""
    if principal.user_id is None:
        raise GrantRequiredError
    now = utcnow()
    async with services.database.session(RlsContext.system()) as session:
        reader = await session.get(ReaderSession, context.reader.id)
        work = await session.get(Work, context.work.id)
        grant = await session.get(Grant, context.grant.id)
        if reader is None or work is None or grant is None:
            raise GrantRequiredError
        reason = ending_reason(reader, grant, work, now)
        if reason is not None:
            raise ReaderSessionEndedError(extra={"reason": reason})
        page_count = (
            await session.scalar(
                select(func.count()).select_from(Page).where(Page.work_id == work.id)
            )
            or 0
        )
        wanted = validate_pages(pages, page_count=int(page_count), grant=grant)
        remaining = await quota_remaining(session, grant)
        if len(wanted) > remaining:
            raise PrintQuotaError(extra={"quota_remaining": remaining})
        job = PrintJob(
            reader_session_id=reader.id,
            grant_id=grant.id,
            user_id=principal.user_id,
            work_id=work.id,
            pages=wanted,
            state=PrintJobState.QUEUED,
            created_by=principal.user_id,
        )
        session.add(job)
        grant.print_used = grant.print_quota - (remaining - len(wanted))
        await session.flush()
        await session.refresh(job)
        remaining -= len(wanted)
        await audit.write(
            session,
            actor_id=principal.id,
            actor_type="user",
            actor_roles=principal.roles,
            action="print.request",
            resource_kind="work",
            resource_id=work.public_id,
            outcome=AuditOutcome.SUCCESS,
            details={
                "job": job.public_id,
                "grant": grant.public_id,
                "session": reader.public_id,
                "pages": wanted,
                "quota_remaining": remaining,
            },
            ip=facts.ip,
            user_agent=facts.user_agent,
            request_id=facts.request_id,
        )
        out = job_out(job, work.public_id, grant.public_id, remaining)
        job_id = job.id
    dispatcher.send(RENDER_TASK, job_id=str(job_id))
    return out


async def view_job(services: ReaderServices, job: PrintJob) -> PrintJobOut:
    async with services.database.session(RlsContext.system()) as session:
        fresh = await session.get(PrintJob, job.id)
        work = await session.get(Work, job.work_id)
        grant = await session.get(Grant, job.grant_id)
        if fresh is None or work is None or grant is None:  # pragma: no cover - foreign keys
            raise GrantRequiredError
        return job_out(
            fresh, work.public_id, grant.public_id, await quota_remaining(session, grant)
        )


# --- Rendering (runs in the worker) ----------------------------------------------------------


@dataclasses.dataclass(frozen=True, slots=True)
class _RenderFacts:
    job_public_id: str
    work_public_id: str
    grant_public_id: str
    title: str
    tag: str
    forensic_key: bytes | None
    pages: list[tuple[int, str, int | None, int | None]]


async def _render_pdf(
    source: ImageSource, settings: Settings, facts: _RenderFacts, at: dt.datetime
) -> bytes:
    # libvips-backed modules are imported here, where the worker renders, so importing the API
    # application (the OpenAPI export, the routes) never loads libvips.
    from jdhp_api.modules.reader import forensic
    from jdhp_api.modules.reader.images import ImageInfo, Region, TileRequest
    from jdhp_api.modules.reader.watermark import print_mark

    images: list[PdfImage] = []
    for seq, key, width, height in facts.pages:
        info = ImageInfo(width, height) if width and height else await source.info(key)
        scale = min(1.0, settings.print_max_edge_px / max(info.width, info.height))
        request = TileRequest(
            region=Region(0, 0, info.width, info.height),
            out_width=max(1, round(info.width * scale)),
            out_height=max(1, round(info.height * scale)),
            rotation=0,
            quality="default",
            format="jpg",
            requested_max=False,
        )
        image = await source.tile(key, request)
        image = print_mark(
            image,
            user_tag=facts.tag,
            grant_public_id=facts.grant_public_id,
            work_public_id=facts.work_public_id,
            at=at,
        )
        if facts.forensic_key is not None:
            image = forensic.embed(image, facts.forensic_key)
        jpeg = bytes(image.jpegsave_buffer(Q=JPEG_QUALITY, strip=True, optimize_coding=True))
        images.append(
            PdfImage(jpeg=jpeg, width=image.width, height=image.height, gray=image.bands == 1)
        )
        del seq
    return build_pdf(
        images,
        ppi=settings.print_ppi,
        title=facts.title,
        subject=f"{facts.work_public_id} · {facts.grant_public_id} · {facts.tag}",
        producer=PRODUCER,
        created_at=at,
    )


async def render_print(
    *,
    database: Database,
    store: ObjectStore,
    settings: Settings,
    forensic_keys: ForensicKeys,
    job_id: uuid.UUID,
    source: ImageSource | None = None,
    now: dt.datetime | None = None,
) -> dict[str, object]:
    """Render one queued job to the exports bucket. Any failure marks the job failed, which
    releases its pages to the quota, and re-raises so the worker logs it."""
    from jdhp_api.modules.reader.images import LibvipsSource

    now = now or utcnow()
    source = source or LibvipsSource(store, settings.bucket_access)
    async with database.session(RlsContext.system()) as session:
        job = await session.get(PrintJob, job_id)
        if job is None:
            return {"job": str(job_id), "status": "missing"}
        if job.state != PrintJobState.QUEUED:
            return {"job": job.public_id, "status": str(job.state)}
        work = await session.get(Work, job.work_id)
        grant = await session.get(Grant, job.grant_id)
        user = await session.get(User, job.user_id)
        reader = (
            await session.get(ReaderSession, job.reader_session_id)
            if job.reader_session_id
            else None
        )
        if work is None or grant is None:  # pragma: no cover - foreign keys
            msg = "print job without its work or grant"
            raise RuntimeError(msg)
        rows = await session.scalars(
            select(Page)
            .where(Page.work_id == job.work_id, Page.seq.in_(job.pages))
            .order_by(Page.seq)
        )
        found = [(p.seq, p.derivative_key, p.width_px, p.height_px) for p in rows.all()]
        wanted = len(job.pages)
        facts = _RenderFacts(
            job_public_id=job.public_id,
            work_public_id=work.public_id,
            grant_public_id=grant.public_id,
            title=work.title_ar,
            tag=user_tag(user.keycloak_sub if user else None),
            forensic_key=forensic_keys.session_key(reader.id) if reader else None,
            pages=[],
        )
    key = export_key(facts.job_public_id)
    try:
        # A missing derivative is a render failure like any other: the job is marked failed
        # and its pages return to the quota.
        facts = dataclasses.replace(facts, pages=_page_sources(found, wanted))
        pdf = await _render_pdf(source, settings, facts, now)
        await asyncio.to_thread(
            store.put, settings.bucket_exports, key, pdf, content_type="application/pdf"
        )
    except Exception as exc:
        async with database.session(RlsContext.system()) as session:
            failed = await session.get(PrintJob, job_id)
            if failed is not None:
                failed.state = PrintJobState.FAILED
                failed.error_detail = f"{type(exc).__name__}: {exc}"[:500]
                await _system_audit(
                    session,
                    "print.failed",
                    facts,
                    outcome=AuditOutcome.FAILURE,
                    details={"error": failed.error_detail},
                )
        raise
    async with database.session(RlsContext.system()) as session:
        ready = await session.get(PrintJob, job_id)
        if ready is not None:
            ready.state = PrintJobState.READY
            ready.rendered_at = now
            ready.export_key = key
            await _system_audit(
                session,
                "print.render",
                facts,
                outcome=AuditOutcome.SUCCESS,
                details={"pages": [seq for seq, *_ in facts.pages], "bytes": len(pdf)},
            )
    return {
        "job": facts.job_public_id,
        "status": "ready",
        "pages": len(facts.pages),
        "bytes": len(pdf),
    }


def _page_sources(
    found: Sequence[tuple[int, str | None, int | None, int | None]], wanted: int
) -> list[tuple[int, str, int | None, int | None]]:
    """Every requested page with its derivative, or the reason the render cannot run."""
    pages: list[tuple[int, str, int | None, int | None]] = []
    for seq, key, width, height in found:
        if not key:
            msg = f"page {seq} has no access derivative"
            raise RuntimeError(msg)
        pages.append((seq, key, width, height))
    if len(pages) != wanted:
        msg = "print job names pages the work does not have"
        raise RuntimeError(msg)
    return pages


async def _system_audit(
    session: AsyncSession,
    action: str,
    facts: _RenderFacts,
    *,
    outcome: AuditOutcome,
    details: dict[str, object],
) -> None:
    await audit.write(
        session,
        actor_id="system",
        actor_type="system",
        actor_roles=("system",),
        action=action,
        resource_kind="work",
        resource_id=facts.work_public_id,
        outcome=outcome,
        severity=AuditSeverity.INFO if outcome == AuditOutcome.SUCCESS else AuditSeverity.NOTICE,
        details={"job": facts.job_public_id, "grant": facts.grant_public_id, **details},
    )


# --- Download: a single-use, fifteen-minute link (SEC-15) ------------------------------------


async def mint_download_link(
    services: ReaderServices, *, job: PrintJob, principal: Principal, facts: RequestFacts
) -> PrintLinkOut:
    now = utcnow()
    settings = services.settings
    async with services.database.session(RlsContext.system()) as session:
        fresh = await session.get(PrintJob, job.id)
        work = await session.get(Work, job.work_id)
        if fresh is None or work is None or fresh.state != PrintJobState.READY:
            raise PrintNotReadyError
        token = secrets.token_urlsafe(TOKEN_BYTES)
        fresh.token_hash = token_hash(token)
        fresh.token_expires_at = now + dt.timedelta(seconds=settings.download_url_ttl_seconds)
        expires_at = fresh.token_expires_at
        await audit.write(
            session,
            actor_id=principal.id,
            actor_type="user",
            actor_roles=principal.roles,
            action="print.link",
            resource_kind="work",
            resource_id=work.public_id,
            outcome=AuditOutcome.SUCCESS,
            details={"job": fresh.public_id, "expires_at": expires_at.isoformat()},
            ip=facts.ip,
            user_agent=facts.user_agent,
            request_id=facts.request_id,
        )
        base = str(settings.api_base_url).rstrip("/")
        url = f"{base}/reader/prints/{fresh.public_id}/file?t={token}"
    return PrintLinkOut(url=url, expires_at=expires_at)


async def deliver(
    services: ReaderServices,
    store: ObjectStore,
    *,
    job: PrintJob,
    principal: Principal,
    facts: RequestFacts,
) -> tuple[bytes, str]:
    """Hand over the PDF once. The row is locked so two requests with the same token cannot
    both succeed; the object is deleted after delivery."""
    now = utcnow()
    async with services.database.session(RlsContext.system()) as session:
        fresh = (
            await session.execute(select(PrintJob).where(PrintJob.id == job.id).with_for_update())
        ).scalar_one()
        work = await session.get(Work, job.work_id)
        if (
            work is None
            or fresh.state != PrintJobState.READY
            or fresh.export_key is None
            or fresh.token_hash is None
            or fresh.token_expires_at is None
            or now >= fresh.token_expires_at
        ):
            raise ForbiddenError
        key = fresh.export_key
        data = await asyncio.to_thread(store.get, services.settings.bucket_exports, key)
        fresh.state = PrintJobState.DOWNLOADED
        fresh.downloaded_at = now
        fresh.token_hash = None
        fresh.token_expires_at = None
        await audit.write(
            session,
            actor_id=principal.id,
            actor_type="user" if principal.authenticated else "anonymous",
            actor_roles=principal.roles,
            action="print.download",
            resource_kind="work",
            resource_id=work.public_id,
            outcome=AuditOutcome.SUCCESS,
            details={"job": fresh.public_id, "pages": list(fresh.pages), "bytes": len(data)},
            ip=facts.ip,
            user_agent=facts.user_agent,
            request_id=facts.request_id,
        )
        filename = f"{work.public_id}-{fresh.public_id}.pdf"
    await asyncio.to_thread(store.delete, services.settings.bucket_exports, key)
    return data, filename
