"""Catalog routes: visibility, identifiers, citations, sample ranges, caching (CAT-1, CAT-5)."""

from __future__ import annotations

import re
from collections.abc import Callable

import httpx
from sqlalchemy import select

from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.orm import AccessClass, PublishState
from jdhp_api.modules.admin.models import RecordChange
from tests.factories import make_author, make_grant, make_user, make_work

UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
Headers = Callable[..., dict[str, str]]


async def test_cat_5_public_list_hides_drafts_embargoed_and_frozen(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        visible = await make_work(session, title_ar="ظاهر")
        await make_work(session, title_ar="مسودة", publish_state=PublishState.DRAFT)
        await make_work(session, title_ar="محظور", access_class=AccessClass.EMBARGOED)
        await make_work(session, title_ar="مجمّد", frozen=True)
    anonymous = await client.get("/works")
    assert anonymous.status_code == 200
    assert [w["public_id"] for w in anonymous.json()["items"]] == [visible.public_id]
    assert anonymous.json()["total"] == 1
    staff = await client.get("/works", headers=auth("carol", ["curator"], mfa=True))
    assert staff.json()["total"] == 4


async def test_cat_5_embargoed_and_draft_resolve_as_not_found_for_the_public(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        embargoed = await make_work(session, access_class=AccessClass.EMBARGOED)
        draft = await make_work(session, publish_state=PublishState.DRAFT)
    for work in (embargoed, draft):
        public = await client.get(f"/works/{work.public_id}")
        assert public.status_code == 404
        assert public.json()["code"] == "not_found"
        member = await client.get(f"/works/{work.public_id}", headers=auth("m", ["member"]))
        assert member.status_code == 404
        staff = await client.get(
            f"/works/{work.public_id}", headers=auth("carol", ["curator"], mfa=True)
        )
        assert staff.status_code == 200


async def test_cat_1_detail_carries_ark_citation_agents_and_no_internal_ids(
    client: httpx.AsyncClient, admin_database: Database
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=5, date_edtf="1923")
        await make_author(session, work)
    response = await client.get(f"/works/{work.public_id}")
    assert response.status_code == 200
    body = response.json()
    assert body["ark"] == f"ark:/99999/{work.public_id}"
    assert body["citation"]["ark"] == body["ark"]
    assert "يعقوب" in body["citation"]["ar"]
    assert "al-Tahhan" in body["citation"]["en"]
    assert body["agents"][0]["role"] == "author"
    assert body["page_count"] == 5
    assert body["rights_basis"] is None
    assert not UUID_RE.search(response.text), "internal identifiers must never appear in responses"


async def test_can_read_reflects_class_and_grant(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        registered = await make_work(session)
        restricted = await make_work(session, access_class=AccessClass.RESTRICTED)
        holder = await make_user(session, "holder")
        await make_grant(session, user=holder, work=restricted)
    anon = await client.get(f"/works/{registered.public_id}")
    assert anon.json()["can_read"] is False
    member = await client.get(f"/works/{registered.public_id}", headers=auth("m", ["member"]))
    assert member.json()["can_read"] is True
    no_grant = await client.get(f"/works/{restricted.public_id}", headers=auth("m", ["member"]))
    assert no_grant.json()["can_read"] is False
    assert no_grant.json()["can_request_access"] is True
    with_grant = await client.get(
        f"/works/{restricted.public_id}", headers=auth("holder", ["member"])
    )
    assert with_grant.json()["can_read"] is True
    assert with_grant.json()["can_request_access"] is False


async def test_cat_1_sample_range_follows_the_access_class(
    client: httpx.AsyncClient, admin_database: Database
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        restricted = await make_work(session, access_class=AccessClass.RESTRICTED, pages=6)
        open_work = await make_work(session, access_class=AccessClass.OPEN, pages=3)
    pages = (await client.get(f"/works/{restricted.public_id}/pages")).json()
    assert [p["in_sample_range"] for p in pages] == [True, True, True, False, False, False]
    assert pages[0]["ark"] == f"ark:/99999/{restricted.public_id}/p1"
    assert all(
        p["in_sample_range"]
        for p in (await client.get(f"/works/{open_work.public_id}/pages")).json()
    )


async def test_cat_4_page_listing_contains_no_ocr_text(
    client: httpx.AsyncClient, admin_database: Database
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=2)
    response = await client.get(f"/works/{work.public_id}/pages")
    assert "سري" not in response.text
    assert "ocr" not in response.text.lower()


async def test_curators_create_and_edit_works_with_change_history(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    curator = auth("carol", ["curator"], mfa=True)
    denied = await client.post("/works", json={"title_ar": "كتاب"}, headers=auth("m", ["member"]))
    assert denied.status_code == 403
    created = await client.post(
        "/works", json={"title_ar": "كتاب جديد", "access_class": "open"}, headers=curator
    )
    assert created.status_code == 201
    name = created.json()["public_id"]
    assert created.json()["publish_state"] == "draft"
    edited = await client.patch(
        f"/works/{name}",
        json={"title_en": "A New Book", "reason": "english title"},
        headers=curator,
    )
    assert edited.status_code == 200
    assert edited.json()["title_en"] == "A New Book"
    forbidden_field = await client.patch(
        f"/works/{name}", json={"access_class": "open"}, headers=curator
    )
    assert forbidden_field.status_code == 422
    async with admin_database.session(RlsContext.system()) as session:
        changes = (await session.scalars(select(RecordChange))).all()
    assert [(c.field, c.new_value) for c in changes] == [("title_en", {"value": "A New Book"})]
    assert changes[0].reason == "english title"


async def test_prf_4_public_responses_cacheable_only_for_anonymous(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session)
    anon = await client.get(f"/works/{work.public_id}")
    assert anon.headers["Cache-Control"] == "public, max-age=60, s-maxage=300"
    member = await client.get(f"/works/{work.public_id}", headers=auth("m", ["member"]))
    assert member.headers["Cache-Control"] == "private, no-store"


async def test_int_7_resolver_maps_a_name_to_its_path(
    client: httpx.AsyncClient, admin_database: Database
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session)
    response = await client.get(f"/resolve/{work.public_id}")
    assert response.json() == {
        "kind": "work",
        "public_id": work.public_id,
        "ark": f"ark:/99999/{work.public_id}",
        "path": f"/works/{work.public_id}",
    }
    assert (await client.get("/resolve/w8nothere0000")).status_code == 404


async def test_list_search_and_filters(client: httpx.AsyncClient, admin_database: Database) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        await make_work(session, title_ar="أخبار سُميرة", access_class=AccessClass.OPEN)
        await make_work(
            session,
            title_ar="رحلة إلى الجبل",
            title_en="Journey",
            access_class=AccessClass.REGISTERED,
        )
    by_title = await client.get("/works", params={"q": "سُميرة"})
    assert by_title.json()["total"] == 1
    by_class = await client.get("/works", params={"access_class": "registered"})
    assert [w["title_en"] for w in by_class.json()["items"]] == ["Journey"]
    paged = await client.get("/works", params={"limit": 1, "offset": 1})
    assert len(paged.json()["items"]) == 1
    assert paged.json()["total"] == 2
