"""Audit viewer (ADM-5): search by user, resource, action and time; chain verification."""

from __future__ import annotations

from collections.abc import Callable

import httpx

from jdhp_api.core.db import Database, RlsContext
from tests.factories import make_work

Headers = Callable[..., dict[str, str]]


async def test_adm_5_rights_officer_searches_the_audit_log(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session)
    await client.get(f"/works/{work.public_id}")
    officer = auth("omar", ["rights_officer"], mfa=True)
    everything = await client.get("/audit/events", headers=officer)
    assert everything.status_code == 200
    assert everything.json()["total"] >= 2
    by_resource = await client.get(
        "/audit/events", headers=officer, params={"resource_id": work.public_id}
    )
    assert {e["action"] for e in by_resource.json()["items"]} == {"authz.view"}
    assert by_resource.json()["items"][0]["actor_id"] == "anonymous"
    by_actor = await client.get(
        "/audit/events", headers=officer, params={"actor": "omar", "action": "authz.list"}
    )
    assert by_actor.json()["total"] >= 1
    verify = await client.get("/audit/verify", headers=officer)
    assert verify.json()["intact"] is True
    assert verify.json()["events_checked"] >= 3


async def test_adm_5_viewer_needs_mfa_and_the_right_role(
    client: httpx.AsyncClient, auth: Headers
) -> None:
    assert (
        await client.get("/audit/events", headers=auth("omar", ["rights_officer"], mfa=False))
    ).status_code == 403
    assert (
        await client.get("/audit/events", headers=auth("carol", ["curator"], mfa=True))
    ).status_code == 403
    assert (
        await client.get("/audit/events", headers=auth("pat", ["platform_admin"], mfa=True))
    ).status_code == 200
