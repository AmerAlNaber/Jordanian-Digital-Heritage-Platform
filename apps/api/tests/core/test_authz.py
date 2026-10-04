"""SEC-6, SEC-25: decisions come from the policy engine, fail closed, and are audited."""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy import func, select

from jdhp_api.core.auth import Principal
from jdhp_api.core.authz import PolicyClient, ResourceRef
from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.errors import PolicyEngineUnavailableError
from jdhp_api.core.orm import AuditOutcome
from jdhp_api.modules.audit.models import AuditEvent


class BrokenPolicyClient:
    async def is_allowed(
        self, principal: Principal, action: str, resource: ResourceRef, request_id: str | None
    ) -> bool:
        raise PolicyEngineUnavailableError

    async def healthy(self) -> bool:
        return False


async def test_sec_6_policy_engine_error_denies(app: FastAPI, client: httpx.AsyncClient) -> None:
    original: PolicyClient = app.state.policy_client
    app.state.policy_client = BrokenPolicyClient()
    try:
        response = await client.get("/works")
    finally:
        app.state.policy_client = original
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "policy_engine_unavailable"


async def test_sec_25_every_decision_is_audited_including_denials(
    client: httpx.AsyncClient, admin_database: Database, auth: Callable[..., dict[str, str]]
) -> None:
    allowed = await client.get("/works")
    assert allowed.status_code == 200
    denied = await client.get("/review/tasks", headers=auth("mallory", ["member"]))
    assert denied.status_code == 403
    async with admin_database.session(RlsContext.system()) as session:
        rows = (await session.scalars(select(AuditEvent).order_by(AuditEvent.seq))).all()
    actions = [(e.action, e.outcome, e.actor_id) for e in rows]
    assert ("authz.list", AuditOutcome.ALLOW, "anonymous") in actions
    assert ("authz.list", AuditOutcome.DENY, "mallory") in actions
    assert all(e.request_id for e in rows)


async def test_anonymous_cannot_use_staff_routes(client: httpx.AsyncClient) -> None:
    for path in ("/review/tasks", "/audit/events", "/intake/batches", "/me"):
        response = await client.get(path)
        assert response.status_code == 403, path


async def test_malformed_bearer_header_is_unauthorized(client: httpx.AsyncClient) -> None:
    response = await client.get("/works", headers={"Authorization": "Basic abc"})
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("token", ["not-a-jwt", "eyJhbGciOiJub25lIn0.e30."])
async def test_garbage_tokens_are_unauthorized(client: httpx.AsyncClient, token: str) -> None:
    response = await client.get("/works", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


async def test_decision_audit_count_matches_requests(
    client: httpx.AsyncClient, admin_database: Database
) -> None:
    for _ in range(3):
        await client.get("/collections")
    async with admin_database.session(RlsContext.system()) as session:
        count = await session.scalar(
            select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "authz.list")
        )
    assert count == 3
