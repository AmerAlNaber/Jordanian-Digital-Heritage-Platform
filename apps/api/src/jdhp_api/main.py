"""Public API application factory.

Everything reachable from the edge is in this application and therefore walked by the
route-coverage test. Health, readiness and metrics live in ``internal_app`` on another port.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from typing import Any

import redis.asyncio as redis_asyncio
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from jdhp_api import __version__
from jdhp_api.core.auth import TokenVerifier, UserSync
from jdhp_api.core.authz import CerbosPolicyClient, PolicyClient
from jdhp_api.core.config import Settings, get_settings
from jdhp_api.core.db import Database
from jdhp_api.core.errors import install_error_handlers
from jdhp_api.core.middleware import RequestContextMiddleware
from jdhp_api.core.observability import configure_logging
from jdhp_api.core.tokens import ForensicKeys, GrantTokenIssuer, TileTokenSigner
from jdhp_api.modules.access.router import router as access_router
from jdhp_api.modules.audit.router import router as audit_router
from jdhp_api.modules.catalog.router import router as catalog_router
from jdhp_api.modules.content.router import router as content_router
from jdhp_api.modules.identity.router import router as identity_router
from jdhp_api.modules.identity.service import DatabaseUserSync
from jdhp_api.modules.ingest.router import router as ingest_router
from jdhp_api.modules.reader.cache import ReaderCache
from jdhp_api.modules.reader.router import router as reader_router
from jdhp_api.modules.reader.service import ReaderServices
from jdhp_api.modules.review.router import router as review_router

API_TITLE = "Jordanian Digital Heritage Platform API"


def create_app(
    settings: Settings | None = None,
    *,
    database: Database | None = None,
    policy_client: PolicyClient | None = None,
    token_verifier: TokenVerifier | None = None,
    user_sync: UserSync | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owns_database = database is None
        app.state.database = database or Database(
            settings.sqlalchemy_url, echo=settings.database_echo
        )
        app.state.policy_client = policy_client or CerbosPolicyClient(settings)
        app.state.token_verifier = token_verifier or TokenVerifier(settings)
        app.state.user_sync = user_sync or DatabaseUserSync(app.state.database)
        redis_client = redis_asyncio.Redis.from_url(str(settings.redis_url))
        app.state.redis = redis_client
        app.state.reader = ReaderServices(
            database=app.state.database,
            settings=settings,
            grant_tokens=GrantTokenIssuer(settings),
            tile_tokens=TileTokenSigner(settings),
            forensic=ForensicKeys(settings),
            cache=ReaderCache(redis_client),
        )
        try:
            yield
        finally:
            await redis_client.aclose()
            if owns_database:
                await app.state.database.dispose()

    app = FastAPI(
        title=API_TITLE,
        version=__version__,
        description=(
            "The core layer of the Jordanian Digital Heritage Platform. Protected content is "
            "served as watermarked tiles only; OCR text is internal and never returned."
        ),
        lifespan=lifespan,
        openapi_url="/openapi.json",
        docs_url="/docs",
        redoc_url=None,
    )
    app.state.settings = settings
    app.add_middleware(RequestContextMiddleware)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[str(origin).rstrip("/") for origin in settings.cors_origins],
            allow_methods=["GET", "POST", "PATCH", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Accept-Language", "X-Request-ID"],
            allow_credentials=False,
        )
    install_error_handlers(app)
    _include_routers(app)
    return app


def _include_routers(app: FastAPI) -> None:
    for router in (
        catalog_router,
        identity_router,
        ingest_router,
        content_router,
        review_router,
        audit_router,
        access_router,
        reader_router,
    ):
        app.include_router(router)


def openapi_document(settings: Settings | None = None) -> dict[str, Any]:
    return create_app(settings).openapi()
