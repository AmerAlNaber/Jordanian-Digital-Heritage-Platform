"""Reader sessions (SEC-2, SEC-5, SEC-10, SEC-11, RDR-1, RDR-5, RDR-6, ACS-2)."""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable
from typing import Any

import httpx
from fastapi import FastAPI
from sqlalchemy import select, update

from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.orm import AccessClass, ReaderSessionState
from jdhp_api.core.tokens import device_hash
from jdhp_api.modules.audit.models import AuditEvent
from jdhp_api.modules.reader.models import ReaderSession
from tests.factories import make_work

Headers = Callable[..., dict[str, str]]
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
FINGERPRINT = "device-fingerprint-alpha"


async def _open(
    client: httpx.AsyncClient,
    work_public_id: str,
    headers: dict[str, str] | None = None,
    *,
    fingerprint: str = FINGERPRINT,
) -> httpx.Response:
    return await client.post(
        "/reader/sessions",
        json={"work": work_public_id, "device_fingerprint": fingerprint},
        headers=headers or {},
    )


def _grant_header(opened: dict[str, Any]) -> dict[str, str]:
    return {"X-Jdhp-Grant": opened["tokens"]["grant_token"]}


async def _heartbeat(
    client: httpx.AsyncClient,
    opened: dict[str, Any],
    *,
    fingerprint: str = FINGERPRINT,
    pages: list[int] | None = None,
) -> httpx.Response:
    return await client.post(
        f"/reader/sessions/{opened['public_id']}/heartbeat",
        json={"device_fingerprint": fingerprint, "pages_viewed": pages or [], "dwell_seconds": 30},
        headers=_grant_header(opened),
    )


async def test_rdr_1_member_opens_a_registered_work_with_bound_credentials(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers, app: FastAPI
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=12)
    response = await _open(client, work.public_id, auth("maha", ["member"]))
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["public_id"].startswith("s8")
    assert body["grant"].startswith("g8")
    assert body["work"] == work.public_id
    assert body["state"] == "active"
    assert body["heartbeat_interval_seconds"] == 60
    assert body["manifest_url"].endswith(f"/reader/works/{work.public_id}/manifest")
    assert body["tiles_base_url"].endswith("/iiif/3")
    assert not UUID_RE.search(response.text), "no internal identifiers leave the API"
    claims = app.state.reader.grant_tokens.verify(body["tokens"]["grant_token"])
    assert claims.session_id == body["public_id"]
    assert claims.subject == "maha"
    assert claims.work_public_id == work.public_id
    assert claims.grant_id == body["grant"]
    assert claims.device_hash == device_hash(FINGERPRINT)
    assert app.state.reader.tile_tokens.verify(body["tokens"]["tile_token"]) == body["public_id"]
    # The session row holds the device hash, never the fingerprint, and a sealed forensic key.
    async with admin_database.session(RlsContext.system()) as session:
        (row,) = (await session.scalars(select(ReaderSession))).all()
    assert row.device_hash == device_hash(FINGERPRINT)
    assert FINGERPRINT.encode() not in row.forensic_key_encrypted
    forensic = app.state.reader.forensic
    assert forensic.open(row.forensic_key_encrypted) == forensic.session_key(row.id)


async def test_sec_2_grant_token_is_bound_to_session_and_device(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=3)
    first = (await _open(client, work.public_id, auth("maha", ["member"]))).json()
    second = (
        await _open(client, work.public_id, auth("nour", ["member"]), fingerprint="device-beta")
    ).json()
    # The right token on the right session with the right device works without a sign-in.
    ok = await _heartbeat(client, first)
    assert ok.status_code == 200, ok.text
    assert ok.json()["tokens"]["grant_token"] != first["tokens"]["grant_token"]
    # A different device fingerprint with a stolen token fails.
    wrong_device = await _heartbeat(client, first, fingerprint="device-gamma")
    assert wrong_device.status_code == 401
    assert wrong_device.json()["code"] == "grant_token_invalid"
    # A token used against another session fails.
    crossed = await client.post(
        f"/reader/sessions/{second['public_id']}/heartbeat",
        json={"device_fingerprint": "device-beta", "pages_viewed": [], "dwell_seconds": 1},
        headers=_grant_header(first),
    )
    assert crossed.status_code == 403
    # No token at all, and a tampered token, fail.
    missing = await client.post(
        f"/reader/sessions/{first['public_id']}/heartbeat",
        json={"device_fingerprint": FINGERPRINT, "pages_viewed": [], "dwell_seconds": 1},
    )
    assert missing.status_code == 401
    assert missing.headers["www-authenticate"] == "Grant"
    tampered = await client.post(
        f"/reader/sessions/{first['public_id']}/heartbeat",
        json={"device_fingerprint": FINGERPRINT, "pages_viewed": [], "dwell_seconds": 1},
        headers={"X-Jdhp-Grant": first["tokens"]["grant_token"][:-4] + "AAAA"},
    )
    assert tampered.status_code == 401


async def test_rdr_5_idle_expiry_ends_the_session_and_clears_the_cache(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers, app: FastAPI
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=3)
    opened = (await _open(client, work.public_id, auth("maha", ["member"]))).json()
    cache = app.state.reader.cache
    assert await cache.is_alive(opened["public_id"])
    async with admin_database.session(RlsContext.system()) as session:
        await session.execute(
            update(ReaderSession).values(
                idle_expires_at=dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
            )
        )
    ended = await _heartbeat(client, opened)
    assert ended.status_code == 401
    assert ended.json()["code"] == "reader_session_ended"
    assert ended.json()["reason"] == "idle"
    assert not await cache.is_alive(opened["public_id"])
    async with admin_database.session(RlsContext.system()) as session:
        (row,) = (await session.scalars(select(ReaderSession))).all()
    assert row.state == ReaderSessionState.EXPIRED
    assert row.ended_at is not None
    # A dead session cannot be revived by another heartbeat.
    assert (await _heartbeat(client, opened)).status_code == 401


async def test_acs_2_revocation_reaches_the_reader_within_the_cache_window(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers, app: FastAPI
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=3)
    opened = (await _open(client, work.public_id, auth("maha", ["member"]))).json()
    officer = auth("omar", ["rights_officer"], mfa=True)
    revoked = await client.post(
        f"/access/grants/{opened['grant']}/revoke",
        json={"reason": "rights review"},
        headers=officer,
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked"] is True
    assert revoked.json()["active"] is False
    assert not await app.state.reader.cache.is_alive(opened["public_id"])
    after = await _heartbeat(client, opened)
    assert after.status_code == 401
    assert after.json()["reason"] == "revoked"
    async with admin_database.session(RlsContext.system()) as session:
        (row,) = (await session.scalars(select(ReaderSession))).all()
        actions = set((await session.scalars(select(AuditEvent.action))).all())
    assert row.state == ReaderSessionState.REVOKED
    assert {"reader.session_open", "grant.revoke"} <= actions


async def test_acs_2_device_limit_is_enforced_per_grant(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=3)
    member = auth("maha", ["member"])
    assert (
        await _open(client, work.public_id, member, fingerprint="device-one")
    ).status_code == 201
    assert (
        await _open(client, work.public_id, member, fingerprint="device-two")
    ).status_code == 201
    third = await _open(client, work.public_id, member, fingerprint="device-three")
    assert third.status_code == 403
    assert third.json()["code"] == "device_limit"
    # The same device may open again; another member has their own grant and limit.
    assert (
        await _open(client, work.public_id, member, fingerprint="device-one")
    ).status_code == 201
    assert (
        await _open(client, work.public_id, auth("nour", ["member"]), fingerprint="device-three")
    ).status_code == 201


async def test_open_works_read_anonymously_and_registered_works_need_a_sign_in(
    client: httpx.AsyncClient, admin_database: Database
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        open_work = await make_work(session, access_class=AccessClass.OPEN, pages=2)
        registered = await make_work(session, pages=2)
        restricted = await make_work(session, access_class=AccessClass.RESTRICTED, pages=2)
    anonymous = await _open(client, open_work.public_id)
    assert anonymous.status_code == 201, anonymous.text
    assert anonymous.json()["grant"] is None
    assert (await _heartbeat(client, anonymous.json())).status_code == 200
    assert (await _open(client, registered.public_id)).status_code == 404
    assert (await _open(client, restricted.public_id)).status_code == 404


async def test_rdr_1_manifest_has_no_text_and_opens_fully_only_with_a_grant_token(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=12)
    url = f"/reader/works/{work.public_id}/manifest"
    public = await client.get(url)
    assert public.status_code == 200
    assert public.headers["content-type"].startswith("application/ld+json")
    assert public.headers["cache-control"] == "private, no-store"
    manifest = public.json()
    assert manifest["type"] == "Manifest"
    assert manifest["viewingDirection"] == "right-to-left"
    assert len(manifest["items"]) == 10, "visitors see the sample range only"
    opened = (await _open(client, work.public_id, auth("maha", ["member"]))).json()
    full = await client.get(url, headers=_grant_header(opened))
    assert len(full.json()["items"]) == 12
    canvas = full.json()["items"][11]
    assert canvas["width"] == 945
    service = canvas["items"][0]["items"][0]["body"]["service"][0]
    assert service["type"] == "ImageService3"
    assert service["id"].endswith(f"/iiif/3/{work.public_id}-p0012")
    text = full.text
    assert "نص الصفحة" not in text, "OCR text never appears in a manifest"
    assert "annotations" not in text
    assert not UUID_RE.search(text)
    # A token for another work does not unlock this one.
    async with admin_database.session(RlsContext.system()) as session:
        other = await make_work(session, pages=2)
    other_session = (await _open(client, other.public_id, auth("maha", ["member"]))).json()
    assert len((await client.get(url, headers=_grant_header(other_session))).json()["items"]) == 10


async def test_rdr_6_heartbeat_records_reading_in_the_audit_log_and_closing_ends_it(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=5)
    opened = (await _open(client, work.public_id, auth("maha", ["member"]))).json()
    beat = await _heartbeat(client, opened, pages=[3, 4])
    assert beat.status_code == 200
    closed = await client.delete(
        f"/reader/sessions/{opened['public_id']}", headers=_grant_header(opened)
    )
    assert closed.status_code == 204
    async with admin_database.session(RlsContext.system()) as session:
        events = (await session.scalars(select(AuditEvent).order_by(AuditEvent.seq))).all()
    heartbeat_events = [e for e in events if e.action == "reader.heartbeat"]
    assert heartbeat_events[0].details["pages"] == [3, 4]
    assert heartbeat_events[0].details["dwell_seconds"] == 30
    assert heartbeat_events[0].resource_id == work.public_id
    assert heartbeat_events[0].actor_id == "maha"
    assert any(e.action == "reader.session_end" and e.details["reason"] == "closed" for e in events)
    viewed = await client.get(
        f"/reader/sessions/{opened['public_id']}",
        headers=auth("omar", ["rights_officer"], mfa=True),
    )
    assert viewed.status_code == 200
    assert viewed.json()["state"] == "expired"
    assert viewed.json()["tokens"] is None
