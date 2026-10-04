"""Digitization intake (ADM-1): manifest validation, registration, dispatch to the pipeline."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.tasks import RecordingDispatcher
from jdhp_api.modules.ingest.models import DigitalObject, Page

Headers = Callable[..., dict[str, str]]


def manifest(pages: int = 3, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "new_work": {
            "title_ar": "أخبار بلدة سُميرة",
            "title_en": "Chronicle of Sumayra",
            "access_class": "registered",
        },
        "item": {
            "shelfmark": "JO-SUM-1923",
            "provenance": "Donated by the author's family (fictional).",
        },
        "capture": {
            "device": "Phase One iXH 150MP",
            "captured_on": "2026-09-01",
            "color_target_ref": "it8-2026-09",
        },
        "staging_prefix": "intake/seed-book",
        "pages": [
            {
                "seq": i,
                "filename": f"{i:04d}.tif",
                "sha256": hashlib.sha256(f"page-{i}".encode()).hexdigest(),
                "label": str(i),
                "page_type": "cover" if i == 1 else "text",
            }
            for i in range(1, pages + 1)
        ],
    }
    body.update(overrides)
    return body


async def test_adm_1_curator_submits_a_batch_and_the_pipeline_is_dispatched(
    client: httpx.AsyncClient,
    admin_database: Database,
    auth: Headers,
    dispatcher: RecordingDispatcher,
) -> None:
    curator = auth("carol", ["curator"], mfa=True)
    response = await client.post("/intake/batches", json=manifest(), headers=curator)
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["state"] == "received"
    assert body["page_count"] == 3
    assert body["code"].startswith("b8")
    assert dispatcher.sent
    assert dispatcher.sent[0][0] == "jdhp.ingest.package"
    async with admin_database.session(RlsContext.system()) as session:
        pages = (await session.scalars(select(Page).order_by(Page.seq))).all()
        digital_objects = (await session.scalars(select(DigitalObject))).all()
    assert [p.seq for p in pages] == [1, 2, 3]
    assert pages[0].page_type.value == "cover"
    assert pages[0].reading_direction.value == "rtl"
    assert pages[0].master_sha256 == hashlib.sha256(b"page-1").hexdigest()
    assert len(digital_objects) == 1
    assert dispatcher.sent[0][1] == {
        "batch_id": str(digital_objects[0].id).replace(
            str(digital_objects[0].id), dispatcher.sent[0][1]["batch_id"]
        )
    }

    fetched = await client.get(f"/intake/batches/{body['code']}", headers=curator)
    assert fetched.status_code == 200
    assert fetched.json()["work_public_id"] == body["work_public_id"]
    listed = await client.get("/intake/batches", headers=curator, params={"state": "received"})
    assert listed.json()["total"] == 1


async def test_adm_1_members_cannot_submit_or_list_batches(
    client: httpx.AsyncClient, auth: Headers
) -> None:
    member = auth("m", ["member"])
    assert (
        await client.post("/intake/batches", json=manifest(), headers=member)
    ).status_code == 403
    assert (await client.get("/intake/batches", headers=member)).status_code == 403


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        (lambda m: m["pages"].pop(1), "gap in sequence"),
        (lambda m: m["pages"][0].update(sha256="xyz"), "bad checksum shape"),
        (lambda m: m["pages"][0].update(filename="../../etc/passwd"), "unsafe filename"),
        (lambda m: m.update(staging_prefix="/absolute"), "absolute prefix"),
        (lambda m: m.update(work_public_id="w8abc"), "two work references"),
        (lambda m: m["pages"][1].update(filename=m["pages"][0]["filename"]), "duplicate filename"),
    ],
)
async def test_sec_17_invalid_manifests_are_rejected(
    client: httpx.AsyncClient, auth: Headers, mutation: Callable[[dict[str, Any]], Any], field: str
) -> None:
    body = manifest()
    mutation(body)
    response = await client.post(
        "/intake/batches", json=body, headers=auth("carol", ["curator"], mfa=True)
    )
    assert response.status_code == 422, field
    assert response.json()["code"] == "validation"


async def test_unknown_existing_work_is_not_found(client: httpx.AsyncClient, auth: Headers) -> None:
    body = manifest()
    body.pop("new_work")
    body["work_public_id"] = "w8nothere0000"
    response = await client.post(
        "/intake/batches", json=body, headers=auth("carol", ["curator"], mfa=True)
    )
    assert response.status_code == 404
