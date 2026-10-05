"""REV-1: an object with origin ai is created pending and invisible outside the review portal.

The zero-leak gate: lists, single reads and the database itself refuse to expose or elevate an
unapproved AI object by any path other than the portal action.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
import pytest
from sqlalchemy import text, update
from sqlalchemy.exc import DBAPIError

from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.orm import Origin, ReviewStatus
from jdhp_api.modules.content.models import ContentObject
from tests.factories import make_content, make_work

Headers = Callable[..., dict[str, str]]

AI_BODY = {
    "provenance_type": "translation",
    "origin": "ai",
    "language": "eng",
    "script": "Latn",
    "body": "In the year the spring ran dry, the town council met beneath the old carob tree.",
    "page_seq": 1,
    "model": "mock-translator",
    "model_version": "1.0",
    "prompt_template_version": "t1",
    "glossary_version": "g1",
    "self_assessment": 0.8,
}


async def test_rev_1_ai_object_invisible_until_approved(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=2)
    curator = auth("carol", ["curator"], mfa=True)
    created = await client.post(f"/works/{work.public_id}/content", json=AI_BODY, headers=curator)
    assert created.status_code == 201, created.text
    public_id = created.json()["public_id"]
    assert created.json()["review_status"] == "pending"

    # Invisible to the public and to members, in lists and by identifier.
    for headers in ({}, auth("m", ["member"])):
        listed = await client.get(f"/works/{work.public_id}/content", headers=headers)
        assert listed.status_code == 200
        assert listed.json() == []
        single = await client.get(f"/content/{public_id}", headers=headers)
        assert single.status_code == 404
        assert "carob" not in listed.text + single.text

    # Visible in the portal.
    reviewer = auth("rana", ["reviewer"], mfa=True)
    assert (await client.get(f"/content/{public_id}", headers=reviewer)).status_code == 200
    tasks = await client.get("/review/tasks", headers=reviewer, params={"state": "pending"})
    assert [t["content_public_id"] for t in tasks.json()["items"]] == [public_id]
    assert tasks.json()["items"][0]["ocr_text"] is not None  # reviewers see the OCR text (ADM-8)

    # Approval through the portal publishes it, labelled as AI-generated and reviewed (SRC-2).
    approved = await client.post(
        f"/review/tasks/{public_id}/approve", json={"note": "good"}, headers=reviewer
    )
    assert approved.status_code == 200, approved.text
    public = await client.get(f"/content/{public_id}")
    assert public.status_code == 200
    body = public.json()
    assert body["review_status"] == "approved"
    assert body["reviewer_subject"] == "rana"
    assert "AI model" in body["label_en"]
    assert "reviewed by" in body["label_en"]
    assert "ذكاء اصطناعي" in body["label_ar"]
    assert [
        c["public_id"] for c in (await client.get(f"/works/{work.public_id}/content")).json()
    ] == [public_id]


async def test_rev_1_review_status_not_settable_via_api(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=1)
    response = await client.post(
        f"/works/{work.public_id}/content",
        json={**AI_BODY, "review_status": "approved"},
        headers=auth("carol", ["curator"], mfa=True),
    )
    assert response.status_code == 422


async def test_rev_1_ai_objects_must_record_their_model(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=1)
    body = {k: v for k, v in AI_BODY.items() if k not in {"model", "model_version"}}
    response = await client.post(
        f"/works/{work.public_id}/content", json=body, headers=auth("carol", ["curator"], mfa=True)
    )
    assert response.status_code == 422


async def test_rev_1_db_guard_blocks_direct_approval(
    database: Database, admin_database: Database
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session)
        obj = await make_content(session, work)
    # A reviewer role without the portal action: refused.
    with pytest.raises(DBAPIError):
        await _set_approved(
            database,
            RlsContext(user_id="", roles=("reviewer",), institution_id=""),
            obj.id,
            flag=False,
        )
    # The portal flag without the reviewer role: refused.
    with pytest.raises(DBAPIError):
        await _set_approved(
            database,
            RlsContext(user_id="", roles=("curator",), institution_id=""),
            obj.id,
            flag=True,
        )
    # The system context: refused too. Only the portal path approves.
    with pytest.raises(DBAPIError):
        await _set_approved(database, RlsContext.system(), obj.id, flag=False)


async def _set_approved(
    database: Database, ctx: RlsContext, content_id: object, *, flag: bool
) -> None:
    async with database.session(ctx) as session:
        if flag:
            await session.execute(text("SELECT set_config('app.review_action', 'approve', true)"))
        await session.execute(
            update(ContentObject)
            .where(ContentObject.id == content_id)
            .values(review_status=ReviewStatus.APPROVED)
        )


async def test_rev_1_ai_objects_start_pending_even_when_inserted_directly(
    database: Database, admin_database: Database
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session)
    with pytest.raises(DBAPIError):
        async with database.session(RlsContext.system()) as session:
            await make_content(
                session,
                work,
                origin=Origin.AI,
                review_status=ReviewStatus.APPROVED,
                with_task=False,
            )


async def test_human_objects_are_visible_without_review(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=1)
    body = {
        "provenance_type": "editorial",
        "origin": "human",
        "language": "ara",
        "script": "Arab",
        "body": "ملاحظة المحرر",
    }
    created = await client.post(
        f"/works/{work.public_id}/content", json=body, headers=auth("carol", ["curator"], mfa=True)
    )
    assert created.status_code == 201
    assert created.json()["review_status"] == "approved"
    assert created.json()["label_ar"].startswith("ملاحظة تحريرية")
    public = await client.get(f"/content/{created.json()['public_id']}")
    assert public.status_code == 200


async def test_src_1_scan_and_ocr_are_not_content_objects(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=1)
    for provenance in ("scan", "ocr"):
        body = {
            "provenance_type": provenance,
            "origin": "human",
            "language": "ara",
            "script": "Arab",
            "body": "x",
        }
        response = await client.post(
            f"/works/{work.public_id}/content",
            json=body,
            headers=auth("carol", ["curator"], mfa=True),
        )
        assert response.status_code == 422, provenance
