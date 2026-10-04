"""Internal application: liveness, readiness and metrics. Served on a port the edge never
routes to, so it is not part of the public router that the route-coverage test walks."""

from __future__ import annotations

from typing import Any

import redis.asyncio as redis_asyncio
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from jdhp_api import __version__
from jdhp_api.core.authz import CerbosPolicyClient
from jdhp_api.core.config import Settings, get_settings
from jdhp_api.core.db import Database


def create_internal_app(
    settings: Settings | None = None, *, database: Database | None = None
) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="jdhp internal", version=__version__, docs_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.database = database
    app.state.policy_client = CerbosPolicyClient(settings)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/readyz")
    async def readyz(request: Request) -> Response:
        checks: dict[str, Any] = {}
        db: Database | None = request.app.state.database
        if db is None:
            db = Database(settings.sqlalchemy_url, pooled=False)
            request.app.state.database = db
        try:
            checks["database"] = await db.ping()
        except Exception:
            checks["database"] = False
        try:
            client = redis_asyncio.Redis.from_url(str(settings.redis_url))
            checks["redis"] = bool(await client.ping())
            await client.aclose()
        except Exception:
            checks["redis"] = False
        checks["policy_engine"] = await request.app.state.policy_client.healthy()
        ready = all(checks.values())
        return JSONResponse({"ready": ready, "checks": checks}, status_code=200 if ready else 503)

    return app
