"""Hash-chained, append-only audit writer (SEC-25, SEC-27).

Each event stores the previous event's hash and its own hash over the canonical JSON of its
content. A transaction-scoped advisory lock serialises writers so the chain never forks. The
details column is redacted before it is hashed, so no token or document ever enters the log.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request

from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.ids import uuid7
from jdhp_api.core.observability import redact_value
from jdhp_api.core.orm import AuditOutcome, AuditSeverity
from jdhp_api.modules.audit.models import GENESIS_HASH, AuditEvent

if TYPE_CHECKING:
    from jdhp_api.core.auth import Principal
    from jdhp_api.core.authz import ResourceRef

CHAIN_LOCK_KEY = "jdhp_audit_chain"


def canonical_json(payload: Mapping[str, Any]) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str
    )


def compute_hash(prev_hash: str, payload: Mapping[str, Any]) -> str:
    return hashlib.sha256((prev_hash + canonical_json(payload)).encode("utf-8")).hexdigest()


def hashed_payload(event: AuditEvent) -> dict[str, Any]:
    """The fields covered by the hash. Everything except the hashes themselves."""
    return {
        "id": str(event.id),
        "occurred_at": event.occurred_at.isoformat(),
        "actor_id": event.actor_id,
        "actor_type": event.actor_type,
        "actor_roles": sorted(event.actor_roles),
        "action": event.action,
        "resource_kind": event.resource_kind,
        "resource_id": event.resource_id,
        "outcome": str(event.outcome),
        "severity": str(event.severity),
        "ip": event.ip,
        "user_agent": event.user_agent,
        "request_id": event.request_id,
        "details": event.details,
    }


async def write(
    session: AsyncSession,
    *,
    actor_id: str,
    actor_type: str,
    actor_roles: Mapping[str, Any] | list[str] | frozenset[str] | tuple[str, ...],
    action: str,
    resource_kind: str,
    resource_id: str,
    outcome: AuditOutcome,
    severity: AuditSeverity = AuditSeverity.INFO,
    details: Mapping[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> AuditEvent:
    """Append one event inside the caller's transaction."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": CHAIN_LOCK_KEY}
    )
    previous = await session.scalar(
        select(AuditEvent.hash).order_by(AuditEvent.seq.desc()).limit(1)
    )
    prev_hash = previous or GENESIS_HASH
    event = AuditEvent(
        id=uuid7(),
        occurred_at=dt.datetime.now(dt.UTC),
        actor_id=actor_id,
        actor_type=actor_type,
        actor_roles=sorted(str(r) for r in actor_roles),
        action=action,
        resource_kind=resource_kind,
        resource_id=resource_id,
        outcome=outcome,
        severity=severity,
        ip=ip,
        user_agent=(user_agent or "")[:512] or None,
        request_id=request_id,
        details=redact_value(dict(details or {})),
        prev_hash=prev_hash,
    )
    event.hash = compute_hash(prev_hash, hashed_payload(event))
    session.add(event)
    await session.flush()
    return event


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return request.client.host if request.client else None


async def record_decision(
    database: Database,
    *,
    principal: Principal,
    action: str,
    ref: ResourceRef,
    allowed: bool,
    request: Request,
) -> None:
    """Every authorization decision is audited, in its own transaction so denials persist."""
    async with database.session(RlsContext.system()) as session:
        await write(
            session,
            actor_id=principal.id,
            actor_type="user" if principal.authenticated else "anonymous",
            actor_roles=principal.roles,
            action=f"authz.{action}",
            resource_kind=ref.kind,
            resource_id=ref.id,
            outcome=AuditOutcome.ALLOW if allowed else AuditOutcome.DENY,
            severity=AuditSeverity.INFO if allowed else AuditSeverity.NOTICE,
            details={"path": request.url.path, "method": request.method},
            ip=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_id=getattr(request.state, "request_id", None),
        )


async def verify_chain(session: AsyncSession, *, limit: int | None = None) -> tuple[bool, int]:
    """Recompute the chain from genesis. Returns (intact, events checked)."""
    stmt = select(AuditEvent).order_by(AuditEvent.seq.asc())
    if limit is not None:
        stmt = stmt.limit(limit)
    result = await session.stream_scalars(stmt)
    expected_prev = GENESIS_HASH
    checked = 0
    async for event in result:
        if event.prev_hash != expected_prev:
            return False, checked
        if compute_hash(event.prev_hash, hashed_payload(event)) != event.hash:
            return False, checked
        expected_prev = event.hash
        checked += 1
    return True, checked
