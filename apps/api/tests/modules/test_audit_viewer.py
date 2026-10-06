"""Audit viewer (ADM-5): search, chain verification, signed exports."""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
from collections.abc import Callable

import httpx
import pytest

from jdhp_api.core.db import Database, RlsContext
from jdhp_api.modules.audit import export as export_module
from jdhp_api.modules.audit.export import ExportSigner
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


async def test_adm_5_export_is_signed_and_audited(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session)
    await client.get(f"/works/{work.public_id}")
    officer = auth("omar", ["rights_officer"], mfa=True)
    key = await client.get("/audit/export/key", headers=officer)
    assert key.status_code == 200
    assert key.json()["algorithm"] == "Ed25519"
    pem = key.json()["public_key_pem"]

    as_json = await client.get(
        "/audit/export", headers=officer, params={"format": "json", "resource_id": work.public_id}
    )
    assert as_json.status_code == 200, as_json.text
    assert as_json.headers["content-type"].startswith("application/json")
    assert as_json.headers["content-disposition"].startswith('attachment; filename="jdhp-audit-')
    body = as_json.content
    digest = "sha-256=" + base64.b64encode(hashlib.sha256(body).digest()).decode()
    assert as_json.headers["digest"] == digest
    scheme, _, signature = as_json.headers["x-jdhp-signature"].partition("=")
    assert scheme == "ed25519"
    assert as_json.headers["x-jdhp-signature-key"] == key.json()["key_id"]
    assert ExportSigner.verify(pem, body, signature) is True
    assert ExportSigner.verify(pem, body + b"x", signature) is False
    document = json.loads(body)
    assert document["format"] == "jdhp-audit-export/1"
    assert document["filters"] == {"resource_id": work.public_id}
    assert [e["action"] for e in document["events"]] == ["authz.view"]
    assert {"prev_hash", "hash", "seq"} <= set(document["events"][0])

    as_csv = await client.get(
        "/audit/export", headers=officer, params={"format": "csv", "resource_id": work.public_id}
    )
    assert as_csv.status_code == 200
    assert as_csv.headers["content-type"].startswith("text/csv")
    text = as_csv.content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    assert rows[0][:3] == ["seq", "occurred_at", "actor_id"]
    assert len(rows) == 2
    assert rows[1][rows[0].index("action")] == "authz.view"
    _, _, csv_signature = as_csv.headers["x-jdhp-signature"].partition("=")
    assert ExportSigner.verify(pem, as_csv.content, csv_signature) is True

    logged = await client.get(
        "/audit/events", headers=officer, params={"action": "audit.export", "actor": "omar"}
    )
    exports = logged.json()["items"]
    assert len(exports) == 2, "every export is itself an audit event (T-D6)"
    assert {e["details"]["format"] for e in exports} == {"csv", "json"}
    assert exports[-1]["details"]["digest"] == digest
    assert exports[-1]["details"]["rows"] == 1


async def test_adm_5_export_refuses_to_truncate(
    client: httpx.AsyncClient,
    admin_database: Database,
    auth: Headers,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session)
    await client.get(f"/works/{work.public_id}")
    await client.get(f"/works/{work.public_id}")
    monkeypatch.setattr(export_module, "EXPORT_MAX_ROWS", 1)
    from jdhp_api.modules.audit import router as audit_router

    monkeypatch.setattr(audit_router, "EXPORT_MAX_ROWS", 1)
    officer = auth("omar", ["rights_officer"], mfa=True)
    too_big = await client.get(
        "/audit/export", headers=officer, params={"resource_id": work.public_id}
    )
    assert too_big.status_code == 400
    assert too_big.json()["code"] == "export_too_large"
    assert too_big.json()["total"] == 2
    assert too_big.json()["limit"] == 1


async def test_adm_5_export_needs_mfa_and_the_right_role(
    client: httpx.AsyncClient, auth: Headers
) -> None:
    assert (
        await client.get("/audit/export", headers=auth("omar", ["rights_officer"], mfa=False))
    ).status_code == 403
    assert (
        await client.get("/audit/export", headers=auth("carol", ["curator"], mfa=True))
    ).status_code == 403
    assert (
        await client.get("/audit/export/key", headers=auth("carol", ["curator"], mfa=True))
    ).status_code == 403
