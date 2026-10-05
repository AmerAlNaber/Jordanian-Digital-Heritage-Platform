"""The tile gateway's request path (RDR-1, RDR-2, SEC-10, SEC-11, SEC-12).

Every tile request is authorized by the policy engine for the page it names, with the
decision cached per reader session and page for sixty seconds. The tile token in the URL
is the only credential: it names the reader session, which names the work, the grant and the
device. Tiles never leave without a mark: the reader's mark on protected pages, the
platform mark on samples and open works. Rate limits run per user and per IP, and exceeding
them suspends the session and flags it in the audit log.
"""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core import audit
from jdhp_api.core.auth import Principal, VerificationLevel, get_principal
from jdhp_api.core.authz import Authorize, Authorized, PolicyClient, ResourceRef, get_policy_client
from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.deps import get_database, get_session
from jdhp_api.core.errors import (
    ForbiddenError,
    GrantTokenError,
    InvalidIdentifierError,
    NotFoundError,
    RateLimitedError,
    ReaderSessionEndedError,
)
from jdhp_api.core.ids import is_valid_name
from jdhp_api.core.orm import AccessClass, AuditOutcome, AuditSeverity
from jdhp_api.core.ratelimit import RateLimiter
from jdhp_api.modules.access.models import Grant
from jdhp_api.modules.catalog import service as catalog_service
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.identity.models import User
from jdhp_api.modules.ingest.models import Page
from jdhp_api.modules.reader import forensic
from jdhp_api.modules.reader import service as reader_service
from jdhp_api.modules.reader.images import (
    ImageInfo,
    ImageSource,
    encode,
    info_document,
    parse_request,
)
from jdhp_api.modules.reader.models import ReaderSession
from jdhp_api.modules.reader.service import ReaderServices, RequestFacts
from jdhp_api.modules.reader.watermark import platform_mark, session_mark

TILE_TOKEN_QUERY = "t"  # noqa: S105  # nosec B105  # a query parameter name, not a secret
PUBLIC_TILE_CACHE = "public, max-age=300"
PRIVATE_TILE_CACHE = "private, no-store"
USER_TAG_LENGTH = 8

router = APIRouter(prefix="/iiif/3", tags=["tiles"])


@dataclasses.dataclass(slots=True)
class TileContext:
    """Everything a tile response needs, resolved once per request."""

    work: Work
    page: Page
    seq: int
    reader: ReaderSession | None
    grant: Grant | None
    principal: Principal
    user_tag: str

    @property
    def protected(self) -> bool:
        return self.work.access_class != AccessClass.OPEN

    @property
    def session_public_id(self) -> str | None:
        return self.reader.public_id if self.reader is not None else None


def principal_for(user: User | None) -> Principal:
    """The principal a tile request acts as: the session's user, or an anonymous visitor."""
    if user is None:
        return Principal.anonymous()
    return Principal(
        id=user.keycloak_sub,
        roles=frozenset({str(user.role)}),
        authenticated=True,
        verification_level=VerificationLevel(str(user.verification_level)),
        institution_id=user.institution_id,
        user_id=user.id,
    )


def user_tag(user: User | None) -> str:
    return user.keycloak_sub[:USER_TAG_LENGTH] if user is not None else "visitor"


async def load_page_for_tile(
    request: Request, _session: AsyncSession, _principal: Principal
) -> tuple[TileContext, ResourceRef]:
    """Resolve the IIIF identifier and the tile token into a page and an effective principal."""
    identifier = str(request.path_params.get("identifier", ""))
    parsed = reader_service.parse_page_identifier(identifier)
    if parsed is None or not is_valid_name(parsed[0]):
        raise InvalidIdentifierError
    name, seq = parsed
    services: ReaderServices = request.app.state.reader
    token = request.query_params.get(TILE_TOKEN_QUERY)
    async with services.database.session(RlsContext.system()) as system:
        work = await catalog_service.get_work_by_name(system, name)
        if work is None:
            raise NotFoundError
        page = (
            await system.scalars(select(Page).where(Page.work_id == work.id, Page.seq == seq))
        ).first()
        if page is None or page.derivative_key is None:
            raise NotFoundError
        reader: ReaderSession | None = None
        grant: Grant | None = None
        user: User | None = None
        if token:
            session_public_id = services.tile_tokens.verify(token)
            reader = await reader_service.get_session_by_public_id(system, session_public_id)
            if reader is None or reader.work_id != work.id:
                raise GrantTokenError
            grant = await system.get(Grant, reader.grant_id) if reader.grant_id else None
            reason = reader_service.ending_reason(reader, grant, work, dt.datetime.now(dt.UTC))
            if reason is not None:
                raise ReaderSessionEndedError(extra={"reason": reason})
            user = await system.get(User, reader.user_id) if reader.user_id else None
    context = TileContext(
        work=work,
        page=page,
        seq=seq,
        reader=reader,
        grant=grant,
        principal=principal_for(user),
        user_tag=user_tag(user),
    )
    attr = catalog_service.page_attributes(work, seq, grant)
    return context, ResourceRef(
        kind="page", id=reader_service.page_identifier(work.public_id, seq), attr=attr
    )


class TileAuthorize(Authorize):
    """``Authorize`` for tiles: the session's principal decides, decisions are cached per
    session and page, and only cache misses and denials reach the audit log."""

    async def __call__(
        self,
        request: Request,
        principal: Principal = Depends(get_principal),
        session: AsyncSession = Depends(get_session),
        policy: PolicyClient = Depends(get_policy_client),
        database: Database = Depends(get_database),
    ) -> Authorized:
        request_id = getattr(request.state, "request_id", None)
        if self.loader is None:  # pragma: no cover - every tile route names the loader
            msg = "tile routes need a loader"
            raise RuntimeError(msg)
        context, ref = await self.loader(request, session, principal)
        effective: Principal = context.principal
        cache = request.app.state.reader.cache
        cached: bool | None = None
        if context.reader is not None:
            try:
                cached = await cache.get_decision(context.reader.public_id, context.seq)
            except (RedisError, OSError):
                cached = None  # Redis trouble means a fresh decision, never an allowance
        if cached is None:
            allowed = await policy.is_allowed(effective, self.action, ref, request_id)
            await audit.record_decision(
                database,
                principal=effective,
                action=self.action,
                ref=ref,
                allowed=allowed,
                request=request,
            )
            if context.reader is not None:
                with contextlib.suppress(RedisError, OSError):
                    await cache.put_decision(context.reader.public_id, context.seq, allowed=allowed)
        else:
            allowed = cached
        if not allowed:
            raise ForbiddenError
        return Authorized(
            principal=effective,
            session=session,
            resource=context,
            ref=ref,
            request_id=request_id,
            action=self.action,
        )


def _facts(request: Request, request_id: str | None) -> RequestFacts:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip()[:45] if forwarded else None
    if ip is None and request.client:
        ip = request.client.host
    return RequestFacts(request_id=request_id, ip=ip, user_agent=request.headers.get("user-agent"))


async def _enforce_rate_limits(request: Request, authorized: Authorized) -> None:
    context: TileContext = authorized.resource
    limiter: RateLimiter = request.app.state.rate_limiter
    facts = _facts(request, authorized.request_id)
    allowed = True
    if facts.ip:
        allowed = await limiter.hit("ip", facts.ip)
    if allowed and context.principal.authenticated:
        allowed = await limiter.hit("user", context.principal.id)
    if allowed:
        return
    if context.reader is not None:
        await reader_service.suspend_session(
            request.app.state.reader,
            reader=context.reader,
            reason="rate_limit",
            principal=context.principal,
            facts=facts,
        )
    else:
        async with request.app.state.reader.database.session(RlsContext.system()) as system:
            await audit.write(
                system,
                actor_id=context.principal.id,
                actor_type="anonymous",
                actor_roles=context.principal.roles,
                action="reader.rate_limited",
                resource_kind="work",
                resource_id=context.work.public_id,
                outcome=AuditOutcome.DENY,
                severity=AuditSeverity.HIGH,
                details={"scope": "ip"},
                ip=facts.ip,
                user_agent=facts.user_agent,
                request_id=facts.request_id,
            )
    raise RateLimitedError


def _cache_header(context: TileContext) -> str:
    return PRIVATE_TILE_CACHE if context.reader is not None else PUBLIC_TILE_CACHE


async def _image_info(request: Request, context: TileContext) -> ImageInfo:
    if context.page.width_px and context.page.height_px:
        return ImageInfo(width=context.page.width_px, height=context.page.height_px)
    source: ImageSource = request.app.state.image_source
    return await source.info(context.page.derivative_key or "")


@router.get("/{identifier}/info.json")
async def image_info(
    request: Request,
    authorized: Annotated[Authorized, Depends(TileAuthorize("read", "page", load_page_for_tile))],
) -> JSONResponse:
    context: TileContext = authorized.resource
    settings = request.app.state.settings
    info = await _image_info(request, context)
    service_id = f"{reader_service.tiles_base_url(settings)}/{authorized.ref.id}"
    body: dict[str, Any] = info_document(
        service_id=service_id,
        info=info,
        tile_size=settings.tile_size,
        max_pixels=settings.tile_max_pixels,
    )
    return JSONResponse(
        body,
        media_type='application/ld+json;profile="http://iiif.io/api/image/3/context.json"',
        headers={"Cache-Control": _cache_header(context)},
    )


@router.get("/{identifier}/{region}/{size}/{rotation}/{quality}.{fmt}")
async def image_tile(
    request: Request,
    region: str,
    size: str,
    rotation: str,
    quality: str,
    fmt: str,
    authorized: Annotated[Authorized, Depends(TileAuthorize("read", "page", load_page_for_tile))],
) -> Response:
    context: TileContext = authorized.resource
    settings = request.app.state.settings
    await _enforce_rate_limits(request, authorized)
    info = await _image_info(request, context)
    tile_request = parse_request(
        region=region,
        size=size,
        rotation=rotation,
        quality=quality,
        fmt=fmt,
        info=info,
        max_pixels=settings.tile_max_pixels,
        allow_max=not context.protected,
    )
    source: ImageSource = request.app.state.image_source
    image = await source.tile(context.page.derivative_key or "", tile_request)
    if context.reader is not None and context.protected:
        image = session_mark(
            image,
            user_tag=context.user_tag,
            session_public_id=context.reader.public_id,
            work_public_id=context.work.public_id,
        )
        services: ReaderServices = request.app.state.reader
        image = forensic.embed(image, services.forensic.session_key(context.reader.id))
    else:
        image = platform_mark(image)
    body = encode(image, tile_request.format)
    return Response(
        content=body,
        media_type=tile_request.media_type,
        headers={
            "Cache-Control": _cache_header(context),
            "X-Content-Type-Options": "nosniff",
            "Content-Disposition": "inline",
        },
    )
