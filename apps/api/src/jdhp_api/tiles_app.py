"""Tile gateway application: the reader module's image path, run as its own process.

Caddy routes ``/iiif/*`` here. Every route is authorized by the policy engine for the page
it names (SEC-6), tile tokens are the only credential (SEC-10), every tile carries a mark
(SEC-11, SEC-14) and rate limits suspend abusive sessions (SEC-12). No health route lives
here: the Compose health check opens a TCP connection, and the edge never routes to it.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator

import redis.asyncio as redis_asyncio
from fastapi import FastAPI

from jdhp_api import __version__
from jdhp_api.core.auth import TokenVerifier
from jdhp_api.core.authz import CerbosPolicyClient, PolicyClient
from jdhp_api.core.config import Settings, get_settings
from jdhp_api.core.db import Database
from jdhp_api.core.errors import install_error_handlers
from jdhp_api.core.middleware import RequestContextMiddleware
from jdhp_api.core.observability import configure_logging
from jdhp_api.core.ratelimit import Limits, RateLimiter
from jdhp_api.core.storage import app_store
from jdhp_api.core.tokens import ForensicKeys, GrantTokenIssuer, TileTokenSigner
from jdhp_api.modules.reader.cache import ReaderCache
from jdhp_api.modules.reader.images import ImageSource, make_image_source
from jdhp_api.modules.reader.service import ReaderServices
from jdhp_api.modules.reader.tiles import router as tiles_router


def create_tiles_app(
    settings: Settings | None = None,
    *,
    database: Database | None = None,
    policy_client: PolicyClient | None = None,
    image_source: ImageSource | None = None,
    redis_client: redis_asyncio.Redis | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        owns_database = database is None
        owns_redis = redis_client is None
        app.state.database = database or Database(
            settings.sqlalchemy_url, echo=settings.database_echo
        )
        app.state.policy_client = policy_client or CerbosPolicyClient(settings)
        app.state.token_verifier = TokenVerifier(settings)
        client = redis_client or redis_asyncio.Redis.from_url(str(settings.redis_url))
        app.state.redis = client
        app.state.reader = ReaderServices(
            database=app.state.database,
            settings=settings,
            grant_tokens=GrantTokenIssuer(settings),
            tile_tokens=TileTokenSigner(settings),
            forensic=ForensicKeys(settings),
            cache=ReaderCache(client),
        )
        app.state.image_source = image_source or make_image_source(settings, app_store(settings))
        app.state.rate_limiter = RateLimiter(
            client,
            Limits(
                burst_per_second=settings.tile_rate_burst_pages_per_second
                * settings.tiles_per_page_estimate,
                sustained_per_minute=settings.tile_rate_sustained_per_minute,
            ),
        )
        try:
            yield
        finally:
            if owns_redis:
                await client.aclose()
            if owns_database:
                await app.state.database.dispose()

    app = FastAPI(
        title="Jordanian Digital Heritage Platform tile gateway",
        version=__version__,
        lifespan=lifespan,
        openapi_url=None,
        docs_url=None,
        redoc_url=None,
    )
    app.state.settings = settings
    app.add_middleware(RequestContextMiddleware)
    install_error_handlers(app)
    app.include_router(tiles_router)
    return app
