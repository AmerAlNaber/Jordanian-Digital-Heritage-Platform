"""Liveness and readiness live on the internal application, outside the public router."""

from __future__ import annotations

import httpx

from jdhp_api.core.config import Settings
from jdhp_api.core.db import Database
from jdhp_api.internal_app import create_internal_app


async def test_health_and_readiness(settings: Settings, database: Database) -> None:
    app = create_internal_app(settings, database=database)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://internal") as client:
        health = await client.get("/healthz")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"
        ready = await client.get("/readyz")
        assert ready.status_code == 200, ready.text
        assert ready.json()["checks"] == {"database": True, "redis": True, "policy_engine": True}
