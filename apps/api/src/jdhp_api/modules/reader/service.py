"""Reader sessions: what turns a grant into tiles (SEC-2, SEC-10, SEC-11, RDR-5, RDR-6).

A session binds a principal, a work, a grant and one device. It carries two credentials the
browser keeps in memory: the grant token for the reader endpoints and the tile token for the
tile URLs. Both are refreshed by the heartbeat, which is also where expiry, revocation and
the device limit are enforced, and where reading analytics land in the audit log.

Reader rows are written under the system context: the grant token, not the row-level
security context of an anonymous browser call, is what proves the caller may touch them.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core import audit
from jdhp_api.core.auth import Principal
from jdhp_api.core.config import Settings
from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.errors import (
    DeviceLimitError,
    GrantRequiredError,
    GrantTokenError,
    ReaderSessionEndedError,
)
from jdhp_api.core.ids import uuid7
from jdhp_api.core.orm import AccessClass, AuditOutcome, AuditSeverity, ReaderSessionState
from jdhp_api.core.tokens import ForensicKeys, GrantClaims, GrantTokenIssuer, TileTokenSigner
from jdhp_api.core.tokens import device_hash as hash_device
from jdhp_api.modules.access import service as access_service
from jdhp_api.modules.access.models import Grant
from jdhp_api.modules.catalog import service as catalog_service
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.ingest.models import Page
from jdhp_api.modules.reader.cache import ReaderCache
from jdhp_api.modules.reader.models import ReaderSession
from jdhp_api.modules.reader.schemas import ReaderSessionOut, ReaderTokens

IIIF_PRESENTATION_CONTEXT = "http://iiif.io/api/presentation/3/context.json"
IMAGE_SERVICE_TYPE = "ImageService3"
IMAGE_SERVICE_PROFILE = "level1"
MANIFEST_MEDIA_TYPE = 'application/ld+json;profile="http://iiif.io/api/presentation/3/context.json"'
RTL_SCRIPTS = frozenset({"Arab", "Hebr", "Syrc"})
ENDED_STATES = frozenset(
    {ReaderSessionState.EXPIRED, ReaderSessionState.REVOKED, ReaderSessionState.SUSPENDED}
)


@dataclasses.dataclass(slots=True)
class ReaderServices:
    """Process-wide helpers the routes hand to the service."""

    database: Database
    settings: Settings
    grant_tokens: GrantTokenIssuer
    tile_tokens: TileTokenSigner
    forensic: ForensicKeys
    cache: ReaderCache


@dataclasses.dataclass(frozen=True, slots=True)
class RequestFacts:
    request_id: str | None
    ip: str | None
    user_agent: str | None


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def page_identifier(work_public_id: str, seq: int) -> str:
    """The IIIF identifier of a page: public work name and page number, never a row id."""
    return f"{work_public_id}-p{seq:04d}"


def parse_page_identifier(identifier: str) -> tuple[str, int] | None:
    name, sep, qualifier = identifier.rpartition("-p")
    if not sep or not name or not qualifier.isdigit():
        return None
    return name, int(qualifier)


def manifest_url(settings: Settings, work_public_id: str) -> str:
    return f"{str(settings.api_base_url).rstrip('/')}/reader/works/{work_public_id}/manifest"


def tiles_base_url(settings: Settings) -> str:
    return f"{str(settings.public_base_url).rstrip('/')}/iiif/3"


def _actor_type(principal: Principal) -> str:
    return "user" if principal.authenticated else "anonymous"


# --- Opening and ending sessions ------------------------------------------------------------


async def _active_device_hashes(
    session: AsyncSession, grant_id: uuid.UUID, now: dt.datetime
) -> set[str]:
    stmt = select(ReaderSession.device_hash).where(
        ReaderSession.grant_id == grant_id,
        ReaderSession.state == ReaderSessionState.ACTIVE,
        ReaderSession.idle_expires_at > now,
        ReaderSession.hard_expires_at > now,
    )
    return set((await session.scalars(stmt)).all())


def _issue_tokens(
    services: ReaderServices,
    reader: ReaderSession,
    subject: str,
    work_public_id: str,
    grant: Grant | None,
) -> ReaderTokens:
    grant_token, grant_expires = services.grant_tokens.issue(
        session_id=reader.public_id,
        subject=subject,
        work_public_id=work_public_id,
        grant_id=grant.public_id if grant else None,
        device_hash=reader.device_hash,
    )
    tile_token, tile_expires = services.tile_tokens.issue(reader.public_id)
    return ReaderTokens(
        grant_token=grant_token,
        grant_token_expires_at=grant_expires,
        tile_token=tile_token,
        tile_token_expires_at=tile_expires,
    )


async def open_session(
    services: ReaderServices,
    *,
    principal: Principal,
    work: Work,
    grant: Grant | None,
    device_fingerprint: str,
    facts: RequestFacts,
) -> ReaderSessionOut:
    """Open a reader session after the policy engine allowed ``read`` on the work."""
    settings = services.settings
    now = utcnow()
    device = hash_device(device_fingerprint)
    async with services.database.session(RlsContext.system()) as session:
        if grant is None and principal.user_id is not None:
            if work.access_class in access_service.CLASS_GRANT_CLASSES:
                grant = await access_service.ensure_class_grant(
                    session, user_id=principal.user_id, work=work, settings=settings, now=now
                )
        elif grant is not None:
            grant = await session.get(Grant, grant.id) or grant
        if grant is None and work.access_class != AccessClass.OPEN:
            raise GrantRequiredError
        if grant is not None:
            if not access_service.is_active(grant, now):
                raise GrantRequiredError
            devices = await _active_device_hashes(session, grant.id, now)
            if device not in devices and len(devices) >= grant.device_limit:
                raise DeviceLimitError
        idle_expires = now + dt.timedelta(seconds=settings.reader_idle_timeout_seconds)
        hard_expires = (
            grant.ends_at
            if grant is not None
            else now + dt.timedelta(seconds=settings.anonymous_session_max_seconds)
        )
        reader_id = uuid7()
        reader = ReaderSession(
            id=reader_id,
            user_id=principal.user_id,
            work_id=work.id,
            grant_id=grant.id if grant else None,
            device_hash=device,
            forensic_key_encrypted=services.forensic.seal(services.forensic.session_key(reader_id)),
            state=ReaderSessionState.ACTIVE,
            last_seen_at=now,
            idle_expires_at=idle_expires,
            hard_expires_at=hard_expires,
            created_by=principal.user_id,
        )
        session.add(reader)
        await session.flush()
        await audit.write(
            session,
            actor_id=principal.id,
            actor_type=_actor_type(principal),
            actor_roles=principal.roles,
            action="reader.session_open",
            resource_kind="work",
            resource_id=work.public_id,
            outcome=AuditOutcome.SUCCESS,
            details={
                "session": reader.public_id,
                "grant": grant.public_id if grant else None,
                "access_class": str(work.access_class),
            },
            ip=facts.ip,
            user_agent=facts.user_agent,
            request_id=facts.request_id,
        )
        tokens = _issue_tokens(services, reader, principal.id, work.public_id, grant)
        out = session_out(
            settings, reader, work.public_id, grant.public_id if grant else None, tokens
        )
    await services.cache.touch(reader.public_id, settings.reader_idle_timeout_seconds)
    return out


def ending_reason(
    reader: ReaderSession, grant: Grant | None, work: Work | None, now: dt.datetime
) -> str | None:
    """Why a session can no longer serve tiles, or None while it still can (RDR-5, ACS-2)."""
    checks: tuple[tuple[bool, str], ...] = (
        (reader.state in ENDED_STATES, str(reader.state)),
        (now >= reader.hard_expires_at, "expired"),
        (now >= reader.idle_expires_at, "idle"),
        (grant is not None and grant.revoked, "revoked"),
        (grant is not None and now >= grant.ends_at, "expired"),
        (work is not None and work.frozen, "frozen"),
    )
    return next((reason for failed, reason in checks if failed), None)


def _state_for(reason: str) -> ReaderSessionState:
    if reason == "revoked":
        return ReaderSessionState.REVOKED
    if reason == "suspended":
        return ReaderSessionState.SUSPENDED
    return ReaderSessionState.EXPIRED


async def _close(
    session: AsyncSession, reader: ReaderSession, *, reason: str, now: dt.datetime
) -> None:
    if reader.state == ReaderSessionState.ACTIVE:
        reader.state = _state_for(reason)
        reader.ended_at = now
        if reader.state in {ReaderSessionState.REVOKED, ReaderSessionState.SUSPENDED}:
            reader.suspended_reason = reason
        await session.flush()


async def heartbeat(
    services: ReaderServices,
    *,
    reader: ReaderSession,
    claims: GrantClaims,
    principal: Principal,
    device_fingerprint: str,
    pages_viewed: Sequence[int],
    dwell_seconds: int,
    facts: RequestFacts,
) -> ReaderSessionOut:
    """Re-validate the session, record what was read, and hand out fresh credentials."""
    settings = services.settings
    now = utcnow()
    if (
        hash_device(device_fingerprint) != reader.device_hash
        or claims.device_hash != reader.device_hash
    ):
        raise GrantTokenError
    async with services.database.session(RlsContext.system()) as session:
        current = await session.get(ReaderSession, reader.id)
        if current is None:
            raise GrantTokenError
        grant = await session.get(Grant, current.grant_id) if current.grant_id else None
        work = await session.get(Work, current.work_id)
        reason = ending_reason(current, grant, work, now)
        if reason is not None or work is None:
            reason = reason or "expired"
            await _close(session, current, reason=reason, now=now)
            await _audit_end(session, principal, current, work, reason, facts)
            session_public_id = current.public_id
        else:
            current.last_seen_at = now
            current.idle_expires_at = now + dt.timedelta(
                seconds=settings.reader_idle_timeout_seconds
            )
            await session.flush()
            await audit.write(
                session,
                actor_id=principal.id if principal.authenticated else claims.subject,
                actor_type=_actor_type(principal),
                actor_roles=principal.roles,
                action="reader.heartbeat",
                resource_kind="work",
                resource_id=work.public_id,
                outcome=AuditOutcome.SUCCESS,
                details={
                    "session": current.public_id,
                    "pages": [int(p) for p in pages_viewed][:100],
                    "dwell_seconds": dwell_seconds,
                },
                ip=facts.ip,
                user_agent=facts.user_agent,
                request_id=facts.request_id,
            )
            tokens = _issue_tokens(services, current, claims.subject, work.public_id, grant)
            out = session_out(
                settings, current, work.public_id, grant.public_id if grant else None, tokens
            )
    if reason is not None:
        await services.cache.clear_session(session_public_id)
        raise ReaderSessionEndedError(extra={"reason": reason})
    await services.cache.touch(current.public_id, settings.reader_idle_timeout_seconds)
    return out


async def _audit_end(
    session: AsyncSession,
    principal: Principal,
    reader: ReaderSession,
    work: Work | None,
    reason: str,
    facts: RequestFacts,
) -> None:
    await audit.write(
        session,
        actor_id=principal.id,
        actor_type=_actor_type(principal),
        actor_roles=principal.roles,
        action="reader.session_end",
        resource_kind="work",
        resource_id=work.public_id if work else str(reader.work_id),
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.NOTICE if reason in {"revoked", "suspended"} else AuditSeverity.INFO,
        details={"session": reader.public_id, "reason": reason},
        ip=facts.ip,
        user_agent=facts.user_agent,
        request_id=facts.request_id,
    )


async def end_session(
    services: ReaderServices, *, reader: ReaderSession, principal: Principal, facts: RequestFacts
) -> None:
    """The reader was closed by its user."""
    now = utcnow()
    async with services.database.session(RlsContext.system()) as session:
        current = await session.get(ReaderSession, reader.id)
        if current is None:
            return
        work = await session.get(Work, current.work_id)
        await _close(session, current, reason="closed", now=now)
        await _audit_end(session, principal, current, work, "closed", facts)
    await services.cache.clear_session(reader.public_id)


async def suspend_session(
    services: ReaderServices,
    *,
    reader: ReaderSession,
    reason: str,
    principal: Principal,
    facts: RequestFacts,
) -> None:
    """Rate limits and anomalies suspend the session and flag it loudly (SEC-12, SEC-26)."""
    now = utcnow()
    async with services.database.session(RlsContext.system()) as session:
        current = await session.get(ReaderSession, reader.id)
        if current is None:
            return
        work = await session.get(Work, current.work_id)
        if current.state == ReaderSessionState.ACTIVE:
            current.state = ReaderSessionState.SUSPENDED
            current.ended_at = now
            current.suspended_reason = reason
            await session.flush()
        await audit.write(
            session,
            actor_id=principal.id,
            actor_type=_actor_type(principal),
            actor_roles=principal.roles,
            action="reader.session_suspended",
            resource_kind="work",
            resource_id=work.public_id if work else str(current.work_id),
            outcome=AuditOutcome.DENY,
            severity=AuditSeverity.HIGH,
            details={"session": current.public_id, "reason": reason},
            ip=facts.ip,
            user_agent=facts.user_agent,
            request_id=facts.request_id,
        )
    await services.cache.clear_session(reader.public_id)


async def end_sessions_for_grant(
    services: ReaderServices, *, grant_id: uuid.UUID, reason: str
) -> int:
    """Revocation reaches every open reader on the grant within the cache window (SEC-5)."""
    now = utcnow()
    ended: list[str] = []
    async with services.database.session(RlsContext.system()) as session:
        stmt = select(ReaderSession).where(
            ReaderSession.grant_id == grant_id, ReaderSession.state == ReaderSessionState.ACTIVE
        )
        for reader in (await session.scalars(stmt)).all():
            await _close(session, reader, reason=reason, now=now)
            ended.append(reader.public_id)
    for public_id in ended:
        await services.cache.clear_session(public_id)
    return len(ended)


async def get_session_by_public_id(session: AsyncSession, public_id: str) -> ReaderSession | None:
    stmt = select(ReaderSession).where(ReaderSession.public_id == public_id)
    return (await session.scalars(stmt)).first()


async def session_view(
    services: ReaderServices, reader: ReaderSession, *, tokens: ReaderTokens | None = None
) -> ReaderSessionOut:
    async with services.database.session(RlsContext.system()) as session:
        work = await session.get(Work, reader.work_id)
        grant = await session.get(Grant, reader.grant_id) if reader.grant_id else None
    work_public_id = work.public_id if work else ""
    return session_out(
        services.settings, reader, work_public_id, grant.public_id if grant else None, tokens
    )


def session_out(
    settings: Settings,
    reader: ReaderSession,
    work_public_id: str,
    grant_public_id: str | None,
    tokens: ReaderTokens | None,
) -> ReaderSessionOut:
    return ReaderSessionOut(
        public_id=reader.public_id,
        work=work_public_id,
        state=reader.state,
        grant=grant_public_id,
        started_at=reader.created_at or utcnow(),
        last_seen_at=reader.last_seen_at,
        idle_expires_at=reader.idle_expires_at,
        hard_expires_at=reader.hard_expires_at,
        heartbeat_interval_seconds=settings.heartbeat_interval_seconds,
        manifest_url=manifest_url(settings, work_public_id),
        tiles_base_url=tiles_base_url(settings),
        tokens=tokens,
    )


# --- IIIF Presentation 3 manifest ----------------------------------------------------------


async def pages_for_manifest(session: AsyncSession, work: Work, *, full: bool) -> list[Page]:
    """Pages the caller may see: all of them with a grant token or on an Open work, else samples."""
    stmt = (
        select(Page)
        .where(Page.work_id == work.id, Page.width_px.is_not(None), Page.height_px.is_not(None))
        .order_by(Page.seq)
    )
    pages = list((await session.scalars(stmt)).all())
    if full or work.access_class == AccessClass.OPEN:
        return pages
    return [p for p in pages if catalog_service.in_sample_range(work, p.seq)]


def manifest(settings: Settings, work: Work, pages: Sequence[Page]) -> dict[str, Any]:
    """A manifest without any text layer: canvases point at the authorizing tile gateway."""
    base = manifest_url(settings, work.public_id)
    tiles = tiles_base_url(settings)
    label: dict[str, list[str]] = {"ar": [work.title_ar]}
    if work.title_en:
        label["en"] = [work.title_en]
    items: list[dict[str, Any]] = []
    for page in pages:
        identifier = page_identifier(work.public_id, page.seq)
        canvas_id = f"{base}/canvas/p{page.seq}"
        items.append(
            {
                "id": canvas_id,
                "type": "Canvas",
                "label": {"none": [page.label or str(page.seq)]},
                "width": page.width_px,
                "height": page.height_px,
                "items": [
                    {
                        "id": f"{canvas_id}/page",
                        "type": "AnnotationPage",
                        "items": [
                            {
                                "id": f"{canvas_id}/image",
                                "type": "Annotation",
                                "motivation": "painting",
                                "body": {
                                    "id": f"{tiles}/{identifier}/full/max/0/default.webp",
                                    "type": "Image",
                                    "format": "image/webp",
                                    "width": page.width_px,
                                    "height": page.height_px,
                                    "service": [
                                        {
                                            "id": f"{tiles}/{identifier}",
                                            "type": IMAGE_SERVICE_TYPE,
                                            "profile": IMAGE_SERVICE_PROFILE,
                                        }
                                    ],
                                },
                                "target": canvas_id,
                            }
                        ],
                    }
                ],
            }
        )
    return {
        "@context": IIIF_PRESENTATION_CONTEXT,
        "id": base,
        "type": "Manifest",
        "label": label,
        "behavior": ["paged"],
        "viewingDirection": "right-to-left" if work.script in RTL_SCRIPTS else "left-to-right",
        "rights": work.rights_statement,
        "requiredStatement": {
            "label": {"ar": ["المصدر"], "en": ["Attribution"]},
            "value": {
                "ar": ["منصة التراث الأردني الرقمي"],
                "en": ["Jordanian Digital Heritage Platform"],
            },
        },
        "items": items,
    }
