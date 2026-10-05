"""Grants (ACS-2): members see their own, rights officers revoke, nobody else does."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from jdhp_api.core.db import Database, RlsContext
from tests.factories import make_work

Headers = Callable[..., dict[str, str]]


async def test_acs_2_member_lists_the_grants_they_hold(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=2)
    maha = auth("maha", ["member"])
    assert (await client.get("/access/grants", headers=maha)).json() == []
    assert (await client.get("/access/grants")).status_code == 403
    opened = await client.post(
        "/reader/sessions",
        json={"work": work.public_id, "device_fingerprint": "device-fingerprint-alpha"},
        headers=maha,
    )
    assert opened.status_code == 201
    grants = (await client.get("/access/grants", headers=maha)).json()
    assert len(grants) == 1
    assert grants[0]["work"] == work.public_id
    assert grants[0]["source"] == "access_class"
    assert grants[0]["active"] is True
    assert grants[0]["device_limit"] == 2
    assert grants[0]["print_quota"] == 20
    assert (await client.get("/access/grants", headers=auth("nour", ["member"]))).json() == []


async def test_acs_2_only_rights_officers_revoke_grants(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=2)
    maha = auth("maha", ["member"])
    await client.post(
        "/reader/sessions",
        json={"work": work.public_id, "device_fingerprint": "device-fingerprint-alpha"},
        headers=maha,
    )
    grant = (await client.get("/access/grants", headers=maha)).json()[0]["public_id"]
    body = {"reason": "testing revocation"}
    assert (
        await client.post(f"/access/grants/{grant}/revoke", json=body, headers=maha)
    ).status_code == 403
    # Row-level security hides other people's grants from curators and visitors (SEC-7).
    assert (
        await client.post(
            f"/access/grants/{grant}/revoke",
            json=body,
            headers=auth("carol", ["curator"], mfa=True),
        )
    ).status_code == 404
    assert (await client.post(f"/access/grants/{grant}/revoke", json=body)).status_code == 404
    assert (
        await client.post(
            "/access/grants/g8nothere/revoke",
            json=body,
            headers=auth("omar", ["rights_officer"], mfa=True),
        )
    ).status_code == 404
    revoked = await client.post(
        f"/access/grants/{grant}/revoke",
        json=body,
        headers=auth("omar", ["rights_officer"], mfa=True),
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["revoked"] is True
    assert (await client.get("/access/grants", headers=maha)).json()[0]["active"] is False
