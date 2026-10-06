"""Audit viewer routes (ADM-5, SEC-25): search by user, resource, action and time."""

from __future__ import annotations

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response

from jdhp_api.core import audit
from jdhp_api.core.authz import Authorize, Authorized
from jdhp_api.core.config import Settings
from jdhp_api.core.deps import current_settings
from jdhp_api.core.errors import ExportTooLargeError
from jdhp_api.core.orm import AuditOutcome, AuditSeverity
from jdhp_api.core.pagination import PageParams, Paginated, page_params
from jdhp_api.modules.audit import service
from jdhp_api.modules.audit.export import EXPORT_MAX_ROWS, ExportSigner, build_export
from jdhp_api.modules.audit.schemas import AuditEventOut, ChainVerification, ExportKeyOut

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/events", response_model=Paginated[AuditEventOut])
async def list_events(
    authorized: Annotated[Authorized, Depends(Authorize("list", "audit_event"))],
    page: Annotated[PageParams, Depends(page_params)],
    actor: Annotated[str | None, Query(max_length=64)] = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
    resource_kind: Annotated[str | None, Query(max_length=32)] = None,
    resource_id: Annotated[str | None, Query(max_length=128)] = None,
    since: dt.datetime | None = None,
    until: dt.datetime | None = None,
) -> Paginated[AuditEventOut]:
    events, total = await service.list_events(
        authorized.session,
        actor=actor,
        action=action,
        resource_kind=resource_kind,
        resource_id=resource_id,
        since=since,
        until=until,
        limit=page.limit,
        offset=page.offset,
    )
    items = [AuditEventOut.model_validate(e, from_attributes=True) for e in events]
    return Paginated(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/verify", response_model=ChainVerification)
async def verify(
    authorized: Annotated[Authorized, Depends(Authorize("verify", "audit_event"))],
) -> ChainVerification:
    intact, checked = await audit.verify_chain(authorized.session)
    return ChainVerification(intact=intact, events_checked=checked)


@router.get(
    "/export",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}, "application/json": {}}}},
)
async def export_events(
    authorized: Annotated[Authorized, Depends(Authorize("export", "audit_event"))],
    settings: Annotated[Settings, Depends(current_settings)],
    format: Literal["csv", "json"] = "json",
    actor: Annotated[str | None, Query(max_length=64)] = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
    resource_kind: Annotated[str | None, Query(max_length=32)] = None,
    resource_id: Annotated[str | None, Query(max_length=128)] = None,
    since: dt.datetime | None = None,
    until: dt.datetime | None = None,
) -> Response:
    """The matching events in chain order, signed (ADM-5). The export itself is audited."""
    filters = {
        "actor": actor,
        "action": action,
        "resource_kind": resource_kind,
        "resource_id": resource_id,
        "since": since.isoformat() if since else None,
        "until": until.isoformat() if until else None,
    }
    events, total = await service.events_for_export(
        authorized.session,
        actor=actor,
        action=action,
        resource_kind=resource_kind,
        resource_id=resource_id,
        since=since,
        until=until,
        max_rows=EXPORT_MAX_ROWS,
    )
    if total > EXPORT_MAX_ROWS:
        raise ExportTooLargeError(extra={"total": total, "limit": EXPORT_MAX_ROWS})
    now = dt.datetime.now(dt.UTC)
    export = build_export(ExportSigner(settings), events, fmt=format, filters=filters, now=now)
    await audit.write(
        authorized.session,
        actor_id=authorized.principal.id,
        actor_type="user",
        actor_roles=authorized.principal.roles,
        action="audit.export",
        resource_kind="audit_event",
        resource_id=f"seq:{events[0].seq}-{events[-1].seq}" if events else "seq:none",
        outcome=AuditOutcome.SUCCESS,
        severity=AuditSeverity.NOTICE,
        details={
            "format": format,
            "filters": {k: v for k, v in filters.items() if v is not None},
            "rows": len(events),
            "digest": export.digest,
            "key_id": export.key_id,
        },
        request_id=authorized.request_id,
    )
    return Response(content=export.body, media_type=export.media_type, headers=export.headers)


@router.get("/export/key", response_model=ExportKeyOut)
async def export_key(
    _authorized: Annotated[Authorized, Depends(Authorize("verify", "audit_event"))],
    settings: Annotated[Settings, Depends(current_settings)],
) -> ExportKeyOut:
    """The public key that verifies export signatures and daily shipments."""
    signer = ExportSigner(settings)
    return ExportKeyOut(
        key_id=signer.key_id, algorithm="Ed25519", public_key_pem=signer.public_key_pem
    )
