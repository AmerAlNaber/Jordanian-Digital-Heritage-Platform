"""The tile gateway (RDR-1, RDR-2, SEC-10, SEC-11, SEC-12): tokens, caps, marks, limits."""

from __future__ import annotations

import datetime as dt
import os
import re
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
import pyvips
import redis.asyncio as redis_asyncio
from fastapi import FastAPI
from moto import mock_aws
from sqlalchemy import select

from jdhp_api.core.config import Settings
from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.orm import AccessClass, ReaderSessionState
from jdhp_api.core.storage import ObjectStore
from jdhp_api.modules.audit.models import AuditEvent
from jdhp_api.modules.ingest.models import Page
from jdhp_api.modules.reader import forensic
from jdhp_api.modules.reader.images import LibvipsSource
from jdhp_api.modules.reader.models import ReaderSession
from jdhp_api.tiles_app import create_tiles_app
from tests.core.test_route_coverage import _has_authorize, api_routes
from tests.factories import make_grant, make_user, make_work

Headers = Callable[..., dict[str, str]]
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
FINGERPRINT = "device-fingerprint-alpha"
PAGE_W, PAGE_H = 945, 1418


def _page_image(seq: int) -> pyvips.Image:
    """A deterministic 'scan': parchment with a dark band whose position depends on the page."""
    base = pyvips.Image.black(PAGE_W, PAGE_H, bands=3).new_from_image([236, 226, 206])
    band = pyvips.Image.black(PAGE_W - 200, 60, bands=3).new_from_image([40, 30, 20])
    return base.insert(band, 100, 200 + (seq * 37) % 900).copy(interpretation="srgb")


@pytest.fixture
def access_store(settings: Settings) -> Any:
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        store = ObjectStore(
            endpoint_url=None, region=settings.s3_region, access_key="testing", secret_key="testing"
        )
        store.ensure_bucket(settings.bucket_access)
        yield store


async def _seed_derivatives(
    admin_database: Database, access_store: ObjectStore, settings: Settings, work_id: Any
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        pages = (await session.scalars(select(Page).where(Page.work_id == work_id))).all()
        for page in pages:
            key = f"{work_id}/{page.digital_object_id}/jp2/{page.seq:04d}.jp2"
            data = _page_image(page.seq).jp2ksave_buffer(Q=80, tile_width=512, tile_height=512)
            access_store.put(settings.bucket_access, key, bytes(data), content_type="image/jp2")
            page.derivative_key = key
            page.width_px, page.height_px = PAGE_W, PAGE_H
        await session.flush()


@pytest_asyncio.fixture
async def tiles(
    settings: Settings, database: Database, access_store: ObjectStore
) -> AsyncIterator[tuple[FastAPI, httpx.AsyncClient]]:
    redis_client = redis_asyncio.Redis.from_url(str(settings.redis_url))
    app = create_tiles_app(
        settings,
        database=database,
        image_source=LibvipsSource(access_store, settings.bucket_access),
        redis_client=redis_client,
    )
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://tiles") as http:
            yield app, http
    await redis_client.aclose()


async def _open(
    client: httpx.AsyncClient, work_public_id: str, headers: dict[str, str] | None = None
) -> dict[str, Any]:
    response = await client.post(
        "/reader/sessions",
        json={"work": work_public_id, "device_fingerprint": FINGERPRINT},
        headers=headers or {},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _tile_url(
    work: str,
    seq: int,
    *,
    region: str = "0,0,512,512",
    size: str = "512,",
    token: str | None = None,
) -> str:
    url = f"/iiif/3/{work}-p{seq:04d}/{region}/{size}/0/default.webp"
    return f"{url}?t={token}" if token else url


def _decode(body: bytes) -> pyvips.Image:
    return pyvips.Image.new_from_buffer(body, "")


async def test_sec_6_every_tiles_route_calls_the_policy_engine(
    tiles: tuple[FastAPI, httpx.AsyncClient],
) -> None:
    app, _ = tiles
    routes = api_routes(app)
    assert len(routes) >= 2
    assert [r.path for r in routes if not _has_authorize(r.dependant)] == []
    assert not {r.path for r in routes} & {"/healthz", "/readyz", "/metrics"}


async def test_rdr_1_sample_tiles_are_public_and_protected_pages_need_a_session(
    tiles: tuple[FastAPI, httpx.AsyncClient],
    client: httpx.AsyncClient,
    admin_database: Database,
    access_store: ObjectStore,
    settings: Settings,
    auth: Headers,
) -> None:
    _, gateway = tiles
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=12)
    await _seed_derivatives(admin_database, access_store, settings, work.id)
    name = work.public_id
    # Sample range without any token: served with the platform mark and a public cache header.
    sample = await gateway.get(_tile_url(name, 10))
    assert sample.status_code == 200, sample.text
    assert sample.headers["content-type"] == "image/webp"
    assert sample.headers["cache-control"] == "public, max-age=300"
    assert _decode(sample.content).width == 512
    # Page 11 of a Registered work is outside the sample range: denied without a session.
    denied = await gateway.get(_tile_url(name, 11))
    assert denied.status_code == 403
    assert denied.json()["code"] == "forbidden"
    # With a member's session the same page is served, privately.
    opened = await _open(client, name, auth("maha", ["member"]))
    token = opened["tokens"]["tile_token"]
    served = await gateway.get(_tile_url(name, 11, token=token))
    assert served.status_code == 200, served.text
    assert served.headers["cache-control"] == "private, no-store"
    assert not UUID_RE.search(served.headers.get("content-disposition", ""))
    # A page that does not exist is not found; a malformed identifier likewise.
    assert (await gateway.get(_tile_url(name, 99, token=token))).status_code == 404
    assert (await gateway.get("/iiif/3/not-an-identifier/info.json")).status_code == 404


async def test_sec_10_tile_tokens_expire_and_bind_to_their_session(
    tiles: tuple[FastAPI, httpx.AsyncClient],
    client: httpx.AsyncClient,
    admin_database: Database,
    access_store: ObjectStore,
    settings: Settings,
    auth: Headers,
) -> None:
    app, gateway = tiles
    async with admin_database.session(RlsContext.system()) as session:
        first = await make_work(session, pages=12)
        second = await make_work(session, pages=12)
    await _seed_derivatives(admin_database, access_store, settings, first.id)
    await _seed_derivatives(admin_database, access_store, settings, second.id)
    opened = await _open(client, first.public_id, auth("maha", ["member"]))
    token = opened["tokens"]["tile_token"]
    # The token works for its own work only.
    assert (await gateway.get(_tile_url(first.public_id, 11, token=token))).status_code == 200
    crossed = await gateway.get(_tile_url(second.public_id, 11, token=token))
    assert crossed.status_code == 401
    assert crossed.json()["code"] == "grant_token_invalid"
    # An expired token is refused: mint one in the past with the gateway's own signer.
    signer = app.state.reader.tile_tokens
    stale, _ = signer.issue(
        opened["public_id"], now=dt.datetime.now(dt.UTC) - dt.timedelta(minutes=6)
    )
    expired = await gateway.get(_tile_url(first.public_id, 11, token=stale))
    assert expired.status_code == 401
    # A tampered token is refused.
    assert (
        await gateway.get(_tile_url(first.public_id, 11, token=token[:-2] + "zz"))
    ).status_code == 401
    # An ended session's token is refused with the reason.
    await client.delete(
        f"/reader/sessions/{opened['public_id']}",
        headers={"X-Jdhp-Grant": opened["tokens"]["grant_token"]},
    )
    ended = await gateway.get(_tile_url(first.public_id, 11, token=token))
    assert ended.status_code == 401
    assert ended.json()["code"] == "reader_session_ended"


async def test_rdr_1_tile_outside_grant_range_denied(
    tiles: tuple[FastAPI, httpx.AsyncClient],
    client: httpx.AsyncClient,
    admin_database: Database,
    access_store: ObjectStore,
    settings: Settings,
    auth: Headers,
) -> None:
    _, gateway = tiles
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, access_class=AccessClass.RESTRICTED, pages=12)
        holder = await make_user(session, "holder")
        await make_grant(session, user=holder, work=work, page_from=4, page_to=8)
    await _seed_derivatives(admin_database, access_store, settings, work.id)
    opened = await _open(client, work.public_id, auth("holder", ["member"]))
    token = opened["tokens"]["tile_token"]
    assert (await gateway.get(_tile_url(work.public_id, 5, token=token))).status_code == 200
    assert (await gateway.get(_tile_url(work.public_id, 9, token=token))).status_code == 403
    # Restricted samples are three pages; page 3 is public, page 4 is not without the grant.
    assert (await gateway.get(_tile_url(work.public_id, 3))).status_code == 200
    assert (await gateway.get(_tile_url(work.public_id, 4))).status_code == 403


async def test_sec_10_full_max_denied_for_protected_work_and_pixel_area_capped(
    tiles: tuple[FastAPI, httpx.AsyncClient],
    client: httpx.AsyncClient,
    admin_database: Database,
    access_store: ObjectStore,
    settings: Settings,
    auth: Headers,
) -> None:
    _, gateway = tiles
    async with admin_database.session(RlsContext.system()) as session:
        protected = await make_work(session, pages=2)
        open_work = await make_work(session, access_class=AccessClass.OPEN, pages=2)
    await _seed_derivatives(admin_database, access_store, settings, protected.id)
    await _seed_derivatives(admin_database, access_store, settings, open_work.id)
    opened = await _open(client, protected.public_id, auth("maha", ["member"]))
    token = opened["tokens"]["tile_token"]
    full_max = await gateway.get(
        _tile_url(protected.public_id, 1, region="full", size="max", token=token)
    )
    assert full_max.status_code == 403
    assert full_max.json()["code"] == "tile_too_large"
    too_many_pixels = await gateway.get(
        _tile_url(protected.public_id, 1, region="full", size=f"{PAGE_W},{PAGE_H}", token=token)
    )
    assert too_many_pixels.status_code == 403
    assert too_many_pixels.json()["code"] == "tile_too_large"
    upscale = await gateway.get(
        _tile_url(protected.public_id, 1, region="0,0,100,100", size="^200,", token=token)
    )
    assert upscale.status_code == 400
    # An Open work answers ``max`` with the largest size inside the cap, never the full page.
    scaled = await gateway.get(_tile_url(open_work.public_id, 1, region="full", size="max"))
    assert scaled.status_code == 200
    image = _decode(scaled.content)
    assert image.width * image.height <= settings.tile_max_pixels
    assert image.width < PAGE_W
    # info.json advertises the cap and only sizes inside it.
    info = (await gateway.get(f"/iiif/3/{protected.public_id}-p0001/info.json?t={token}")).json()
    assert info["maxArea"] == settings.tile_max_pixels
    assert info["tiles"][0]["width"] == settings.tile_size
    assert all(s["width"] * s["height"] <= settings.tile_max_pixels for s in info["sizes"])
    assert info["id"].endswith(f"/iiif/3/{protected.public_id}-p0001")
    assert not UUID_RE.search(str(info))


async def test_sec_11_every_protected_tile_is_watermarked(
    tiles: tuple[FastAPI, httpx.AsyncClient],
    client: httpx.AsyncClient,
    admin_database: Database,
    access_store: ObjectStore,
    settings: Settings,
    auth: Headers,
) -> None:
    _, gateway = tiles
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=12)
    await _seed_derivatives(admin_database, access_store, settings, work.id)
    opened = await _open(client, work.public_id, auth("maha", ["member"]))
    token = opened["tokens"]["tile_token"]
    region = "100,100,512,512"
    served = _decode(
        (await gateway.get(_tile_url(work.public_id, 11, region=region, token=token))).content
    )
    plain = _page_image(11).crop(100, 100, 512, 512)
    assert (served.width, served.height) == (512, 512)
    difference = (served.cast("int") - plain.cast("int")).abs()
    assert difference.max() > 10, "the reader's mark changes the tile"
    assert (difference.bandor() > 4).avg() / 255 > 0.01, (
        "the mark covers a visible share of the tile"
    )
    # Two sessions get different marks (the mark names the session), the same session the same.
    other = await _open(client, work.public_id, auth("nour", ["member"]))
    theirs = _decode(
        (
            await gateway.get(
                _tile_url(work.public_id, 11, region=region, token=other["tokens"]["tile_token"])
            )
        ).content
    )
    assert (served.cast("int") - theirs.cast("int")).abs().max() > 10
    # The forensic mark names the session: detected with its key, not with another's (SEC-11).
    async with admin_database.session(RlsContext.system()) as session:
        rows = {r.public_id: r for r in (await session.scalars(select(ReaderSession))).all()}
    forensic_keys = tiles[0].state.reader.forensic
    mine = forensic_keys.session_key(rows[opened["public_id"]].id)
    theirs_key = forensic_keys.session_key(rows[other["public_id"]].id)
    assert forensic.detect(served, mine).present
    assert not forensic.detect(served, theirs_key).present
    assert forensic.detect(theirs, theirs_key).present
    # Samples carry the platform mark too (SEC-14).
    sample = _decode((await gateway.get(_tile_url(work.public_id, 1, region=region))).content)
    assert (
        sample.cast("int") - _page_image(1).crop(100, 100, 512, 512).cast("int")
    ).abs().max() > 10


async def test_sec_12_tile_rate_limit_suspends_session(
    tiles: tuple[FastAPI, httpx.AsyncClient],
    client: httpx.AsyncClient,
    admin_database: Database,
    access_store: ObjectStore,
    settings: Settings,
    auth: Headers,
) -> None:
    app, gateway = tiles
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=12)
    await _seed_derivatives(admin_database, access_store, settings, work.id)
    opened = await _open(client, work.public_id, auth("maha", ["member"]))
    token = opened["tokens"]["tile_token"]
    app.state.rate_limiter._limits = type(app.state.rate_limiter._limits)(
        burst_per_second=3, sustained_per_minute=600
    )
    # A frozen clock keeps the five requests inside one burst window whatever the load.
    frozen = time.time() + 10_000
    app.state.rate_limiter._clock = lambda: frozen
    statuses = [
        (
            await gateway.get(
                _tile_url(
                    work.public_id, 11, region=f"{i * 10},0,256,256", size="256,", token=token
                )
            )
        ).status_code
        for i in range(5)
    ]
    assert statuses[:3] == [200, 200, 200]
    assert 429 in statuses[3:]
    async with admin_database.session(RlsContext.system()) as session:
        (row,) = (await session.scalars(select(ReaderSession))).all()
        events = (
            await session.scalars(
                select(AuditEvent).where(AuditEvent.action == "reader.session_suspended")
            )
        ).all()
    assert row.state == ReaderSessionState.SUSPENDED
    assert row.suspended_reason == "rate_limit"
    assert events
    assert events[0].severity.value == "high"
    # The suspended session's heartbeat fails with the reason, and its tiles are refused.
    beat = await client.post(
        f"/reader/sessions/{opened['public_id']}/heartbeat",
        json={"device_fingerprint": FINGERPRINT, "pages_viewed": [], "dwell_seconds": 1},
        headers={"X-Jdhp-Grant": opened["tokens"]["grant_token"]},
    )
    assert beat.status_code == 401
    assert beat.json()["reason"] == "suspended"
    assert (await gateway.get(_tile_url(work.public_id, 11, token=token))).status_code == 401


async def test_sec_12_ip_rate_limit_independent_of_user(
    tiles: tuple[FastAPI, httpx.AsyncClient],
    admin_database: Database,
    access_store: ObjectStore,
    settings: Settings,
) -> None:
    app, gateway = tiles
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, access_class=AccessClass.OPEN, pages=2)
    await _seed_derivatives(admin_database, access_store, settings, work.id)
    app.state.rate_limiter._limits = type(app.state.rate_limiter._limits)(
        burst_per_second=2, sustained_per_minute=600
    )
    frozen = time.time() + 20_000  # one burst window for the whole test, whatever the load
    app.state.rate_limiter._clock = lambda: frozen
    one = {"X-Forwarded-For": "203.0.113.7"}
    two = {"X-Forwarded-For": "203.0.113.8"}
    results = [
        (
            await gateway.get(
                _tile_url(work.public_id, 1, region=f"{i},0,128,128", size="128,"), headers=one
            )
        ).status_code
        for i in range(4)
    ]
    assert results[:2] == [200, 200]
    assert 429 in results[2:]
    assert (await gateway.get(_tile_url(work.public_id, 1), headers=two)).status_code == 200


async def test_sec_10_redis_outage_fails_closed_not_open(
    settings: Settings,
    database: Database,
    access_store: ObjectStore,
    client: httpx.AsyncClient,
    admin_database: Database,
    auth: Headers,
) -> None:
    """Without Redis the gateway still asks the policy engine per tile and limits in memory."""
    dead = redis_asyncio.Redis.from_url("redis://127.0.0.1:1/0", socket_connect_timeout=0.2)
    app = create_tiles_app(
        settings,
        database=database,
        image_source=LibvipsSource(access_store, settings.bucket_access),
        redis_client=dead,
    )
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=12)
    await _seed_derivatives(admin_database, access_store, settings, work.id)
    opened = await _open(client, work.public_id, auth("maha", ["member"]))
    token = opened["tokens"]["tile_token"]
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://tiles") as gateway:
            assert (
                await gateway.get(_tile_url(work.public_id, 11, token=token))
            ).status_code == 200
            assert (await gateway.get(_tile_url(work.public_id, 11))).status_code == 403
            assert app.state.rate_limiter.degraded is True
    await dead.aclose()


async def test_sec_10_no_route_serves_originals(
    app: FastAPI, tiles: tuple[FastAPI, httpx.AsyncClient]
) -> None:
    gateway_app, _ = tiles
    paths = [r.path for r in api_routes(app)] + [r.path for r in api_routes(gateway_app)]
    assert not any("preservation" in p or "master" in p or "download" in p for p in paths)
    assert all(p.startswith("/iiif/3/") for p in (r.path for r in api_routes(gateway_app)))


async def test_rdr_1_tile_token_is_accepted_as_a_header(
    tiles: tuple[FastAPI, httpx.AsyncClient],
    client: httpx.AsyncClient,
    admin_database: Database,
    access_store: ObjectStore,
    settings: Settings,
    auth: Headers,
) -> None:
    """The viewer sends the token as a header on every tile request (RDR-1)."""
    _app, gateway = tiles
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=12)
    await _seed_derivatives(admin_database, access_store, settings, work.id)
    opened = await _open(client, work.public_id, auth("maha", ["member"]))
    token = opened["tokens"]["tile_token"]
    url = _tile_url(work.public_id, 11, size="256,", region="0,0,256,256")
    assert (await gateway.get(url)).status_code == 403
    with_header = await gateway.get(url, headers={"X-Jdhp-Tile": token})
    assert with_header.status_code == 200, with_header.text
    assert with_header.headers["content-type"] == "image/webp"
    bad = await gateway.get(url, headers={"X-Jdhp-Tile": token[:-4] + "AAAA"})
    assert bad.status_code == 401
