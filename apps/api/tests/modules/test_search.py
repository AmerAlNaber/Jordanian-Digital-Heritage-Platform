"""Search (SRCH-1 to SRCH-4, CAT-4, CAT-5): Arabic normalization, visibility, regions, no text."""

from __future__ import annotations

import json
import os
import re
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from moto import mock_aws
from sqlalchemy import select

from jdhp_api.core.auth import Principal, TokenVerifier
from jdhp_api.core.authz import CerbosPolicyClient, ResourceRef
from jdhp_api.core.config import Settings
from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.orm import AccessClass, PublishState
from jdhp_api.core.storage import ObjectStore
from jdhp_api.core.tasks import RecordingDispatcher
from jdhp_api.main import create_app
from jdhp_api.modules.access.models import Grant
from jdhp_api.modules.catalog import service as catalog
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.ingest.models import Page
from jdhp_api.modules.search import backend as search_backend
from jdhp_api.modules.search.backend import Filters, InMemoryBackend, pages_query, works_query
from jdhp_api.modules.search.indexer import PageDocument, RecordingIndexer, WorkDocument
from jdhp_api.modules.search.service import regions_from, scan_visible
from tests.factories import make_author, make_work

Headers = Callable[..., dict[str, str]]
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")

# Page texts of the test book. Diacritics on the page, none in the queries (SRCH-3).
PAGE_TEXTS = {
    1: "أخبار بلدة سُمَيْرة\nوما حولها من الوادي والجبل",  # noqa: RUF001
    2: "باب في ذكر وادي الكَرْم وما فيه من المعاصر",
    3: "باب في ذكر السوق والطرق",
    12: "وكان أهل الكَرْم يجمعون الزيتون في تشرين",
    13: "ذكر الجراد وسنة المحل",
}
SECRET_PHRASE = "يجمعون الزيتون في تشرين"


def _word_offsets(text: str) -> list[dict[str, int]]:
    """Offsets like the worker writes: one box per word, boxes laid out line by line."""
    offsets: list[dict[str, int]] = []
    cursor = 0
    for line_no, line in enumerate(text.split("\n")):
        if line_no:
            cursor += 1
        x = 100
        for word_no, word in enumerate(line.split(" ")):
            if word_no:
                cursor += 1
            offsets.append(
                {
                    "start": cursor,
                    "end": cursor + len(word),
                    "x": x,
                    "y": 200 + line_no * 60,
                    "w": 30 * len(word),
                    "h": 48,
                }
            )
            x += 30 * len(word) + 20
            cursor += len(word)
    return offsets


@pytest.fixture
def indexer() -> RecordingIndexer:
    return RecordingIndexer()


@pytest.fixture
def access_store(settings: Settings) -> Any:
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        store = ObjectStore(
            endpoint_url=None, region=settings.s3_region, access_key="testing", secret_key="testing"
        )
        store.ensure_bucket(settings.bucket_access)
        yield store


@pytest_asyncio.fixture
async def app(
    settings: Settings,
    database: Database,
    dispatcher: RecordingDispatcher,
    indexer: RecordingIndexer,
    access_store: ObjectStore,
) -> AsyncIterator[FastAPI]:
    application = create_app(
        settings,
        database=database,
        token_verifier=TokenVerifier(settings),
        search_backend=InMemoryBackend(indexer),
        store=access_store,
    )
    application.state.dispatcher = dispatcher
    async with application.router.lifespan_context(application):
        yield application


def _work_document(work: Work, **extra: Any) -> WorkDocument:
    fields: dict[str, Any] = {
        "work_id": work.id,
        "public_id": work.public_id,
        "title_ar": work.title_ar,
        "title_translit": work.title_translit,
        "title_en": work.title_en,
        "description_ar": work.description_ar,
        "description_en": work.description_en,
        "agents": [],
        "subjects": [],
        "places": [],
        "periods": [],
        "collections": [],
        "language": work.language,
        "date_earliest": None,
        "date_latest": None,
        "access_class": str(work.access_class),
        "publish_state": str(work.publish_state),
        "frozen": work.frozen,
    }
    fields.update(extra)
    return WorkDocument(**fields)


async def _index_work(
    admin_database: Database,
    indexer: RecordingIndexer,
    store: ObjectStore,
    settings: Settings,
    work: Work,
    texts: dict[int, str],
    **extra: Any,
) -> None:
    """Index a work and its pages the way the pipeline does, with offsets in the access bucket."""
    indexer.index_work(_work_document(work, **extra))
    async with admin_database.session(RlsContext.system()) as session:
        pages = (await session.scalars(select(Page).where(Page.work_id == work.id))).all()
        for page in pages:
            text = texts.get(page.seq, f"صفحة {page.seq}")
            page.ocr_text = text
            page.offsets_key = (
                f"{work.id}/{page.digital_object_id}/alto/{page.seq:04d}.offsets.json"
            )
            store.put(
                settings.bucket_access,
                page.offsets_key,
                json.dumps(_word_offsets(text)).encode("utf-8"),
                content_type="application/json",
            )
            indexer.index_page(
                PageDocument(
                    page_id=page.id,
                    work_id=work.id,
                    work_public_id=work.public_id,
                    seq=page.seq,
                    label=page.label,
                    text=text,
                    language="ara",
                    access_class=str(work.access_class),
                    publish_state=str(work.publish_state),
                    frozen=work.frozen,
                )
            )
        await session.flush()


@pytest_asyncio.fixture
async def book(
    admin_database: Database,
    indexer: RecordingIndexer,
    access_store: ObjectStore,
    settings: Settings,
) -> Work:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=14, description_ar="تاريخ محلي لوادي الكَرْم")
        await make_author(session, work)
    await _index_work(
        admin_database,
        indexer,
        access_store,
        settings,
        work,
        PAGE_TEXTS,
        subjects=["agriculture"],
        places=["wadi-al-karm"],
        agents=["يعقوب بن سالم الطحّان"],
    )
    return work


# --- Matching and normalization ---------------------------------------------------------------


async def test_srch_3_query_without_diacritics_matches_text_with_them(
    client: httpx.AsyncClient, book: Work
) -> None:
    response = await client.get("/search", params={"q": "الكرم"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total_works"] == 1
    hit = body["works"][0]
    assert hit["work"]["public_id"] == book.public_id
    assert hit["work"]["ark"] == f"ark:/99999/{book.public_id}"
    assert [p["seq"] for p in hit["pages"]] == [2, 12]
    assert hit["page_hits_total"] == 2
    assert body["total_page_hits"] == 2


async def test_srch_3_hamza_and_ta_marbuta_fold(client: httpx.AsyncClient, book: Work) -> None:
    for query in ("اخبار", "أخبار", "بلده"):
        response = await client.get("/search", params={"q": query})
        assert response.status_code == 200
        assert response.json()["total_works"] == 1, query


async def test_srch_1_latin_title_matches_too(client: httpx.AsyncClient, book: Work) -> None:
    response = await client.get("/search", params={"q": "Sumayra"})
    assert response.json()["total_works"] == 1


async def test_no_match_is_an_empty_result_not_an_error(
    client: httpx.AsyncClient, book: Work
) -> None:
    response = await client.get("/search", params={"q": "zzzz"})
    assert response.status_code == 200
    body = response.json()
    assert body["total_works"] == 0
    assert body["works"] == []


async def test_query_is_required_and_bounded(client: httpx.AsyncClient) -> None:
    assert (await client.get("/search")).status_code == 422
    assert (await client.get("/search", params={"q": "x" * 201})).status_code == 422
    assert (await client.get("/search", params={"q": "x", "limit": 51})).status_code == 422


# --- CAT-4: the response never carries text -----------------------------------------------------


async def test_cat_4_response_carries_regions_and_never_text(
    client: httpx.AsyncClient, book: Work, auth: Headers
) -> None:
    response = await client.get("/search", params={"q": "الزيتون"}, headers=auth("reader"))
    assert response.status_code == 200
    body = response.json()
    assert SECRET_PHRASE not in response.text
    assert "الزيتون" not in json.dumps(body["works"], ensure_ascii=False)
    assert not UUID_RE.search(response.text), "internal identifiers never appear in responses"

    def keys(value: Any) -> set[str]:
        found: set[str] = set()
        if isinstance(value, dict):
            for key, item in value.items():
                found.add(key)
                found |= keys(item)
        elif isinstance(value, list):
            for item in value:
                found |= keys(item)
        return found

    assert not keys(body) & {"text", "ocr_text", "snippet", "highlight", "excerpt"}
    page = body["works"][0]["pages"][0]
    assert page["seq"] == 12
    assert page["scan_visible"] is True  # a signed-in member reads a Registered work
    assert page["ark"] == f"ark:/99999/{book.public_id}/p12"
    word = _word_offsets(PAGE_TEXTS[12])[4]  # the fifth word of the line is الزيتون
    assert page["regions"] == [{"x": word["x"], "y": word["y"], "w": word["w"], "h": word["h"]}]


async def test_srch_4_regions_only_for_pages_the_caller_may_see(
    client: httpx.AsyncClient, book: Work, auth: Headers
) -> None:
    anonymous = (await client.get("/search", params={"q": "الكرم"})).json()
    pages = {p["seq"]: p for p in anonymous["works"][0]["pages"]}
    assert pages[2]["scan_visible"] is True
    assert pages[2]["regions"]
    assert pages[12]["scan_visible"] is False
    assert pages[12]["regions"] == []
    assert pages[12]["thumbnail_available"] is True
    member = (await client.get("/search", params={"q": "الكرم"}, headers=auth("m"))).json()
    pages = {p["seq"]: p for p in member["works"][0]["pages"]}
    assert pages[12]["scan_visible"] is True
    assert len(pages[12]["regions"]) == 1


async def test_regions_from_overlapping_spans_and_malformed_entries() -> None:
    offsets = _word_offsets("ألف باء جيم")
    offsets.append({"start": -1, "end": -1, "x": 0, "y": 0, "w": 0, "h": 0})
    offsets.append({"x": 1})
    regions = regions_from(offsets, [(4, 7)])
    assert len(regions) == 1
    assert regions[0].x == offsets[1]["x"]
    assert regions_from(offsets, []) == []


# --- CAT-5: visibility and facets ---------------------------------------------------------------


async def test_cat_5_public_search_excludes_drafts_embargoed_and_frozen_from_hits_and_facets(
    client: httpx.AsyncClient,
    admin_database: Database,
    indexer: RecordingIndexer,
    access_store: ObjectStore,
    settings: Settings,
    auth: Headers,
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        visible = await make_work(session, title_ar="ديوان ظاهر", pages=1)
        draft = await make_work(
            session, title_ar="ديوان مسودة", pages=1, publish_state=PublishState.DRAFT
        )
        embargoed = await make_work(
            session, title_ar="ديوان محظور", pages=1, access_class=AccessClass.EMBARGOED
        )
        frozen = await make_work(session, title_ar="ديوان مجمّد", pages=1, frozen=True)
    for work, subject in (
        (visible, "poetry"),
        (draft, "draft-only"),
        (embargoed, "embargo-only"),
        (frozen, "frozen-only"),
    ):
        await _index_work(
            admin_database,
            indexer,
            access_store,
            settings,
            work,
            {1: "ديوان شعر"},
            subjects=[subject],
        )
    public = (await client.get("/search", params={"q": "ديوان"})).json()
    assert [w["work"]["public_id"] for w in public["works"]] == [visible.public_id]
    assert public["total_works"] == 1
    assert public["total_page_hits"] == 1
    assert [b["value"] for b in public["facets"]["subjects"]] == ["poetry"]
    assert "embargoed" not in {b["value"] for b in public["facets"]["access_class"]}
    staff = (
        await client.get(
            "/search", params={"q": "ديوان"}, headers=auth("carol", ["curator"], mfa=True)
        )
    ).json()
    assert staff["total_works"] == 4
    assert {b["value"] for b in staff["facets"]["subjects"]} == {
        "poetry",
        "draft-only",
        "embargo-only",
        "frozen-only",
    }


async def test_cat_5_a_stale_index_entry_is_dropped_by_the_database_recheck(
    client: httpx.AsyncClient,
    admin_database: Database,
    indexer: RecordingIndexer,
    access_store: ObjectStore,
    settings: Settings,
) -> None:
    """The index still says published; the database says embargoed. The database wins."""
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, title_ar="رسالة في الفلك", pages=1)
    await _index_work(admin_database, indexer, access_store, settings, work, {1: "الفلك"})
    async with admin_database.session(RlsContext.system()) as session:
        row = await session.get(Work, work.id)
        assert row is not None
        row.access_class = AccessClass.EMBARGOED
        await session.flush()
    body = (await client.get("/search", params={"q": "الفلك"})).json()
    assert body["total_works"] == 0
    assert body["total_page_hits"] == 0


async def test_facet_filters_narrow_the_result(client: httpx.AsyncClient, book: Work) -> None:
    hit = (await client.get("/search", params={"q": "سميرة", "subject": "agriculture"})).json()
    assert hit["total_works"] == 1
    miss = (await client.get("/search", params={"q": "سميرة", "subject": "medicine"})).json()
    assert miss["total_works"] == 0
    assert miss["total_page_hits"] == 0
    # A page match alone cannot bring back a work the subject facet excluded.
    by_page = (await client.get("/search", params={"q": "الزيتون", "subject": "medicine"})).json()
    assert by_page["total_works"] == 0
    by_place = (
        await client.get("/search", params={"q": "الزيتون", "place": "wadi-al-karm"})
    ).json()
    assert by_place["total_works"] == 1
    assert by_place["total_page_hits"] == 1
    by_class = (await client.get("/search", params={"q": "سميرة", "access_class": "open"})).json()
    assert by_class["total_works"] == 0


# --- Scope -------------------------------------------------------------------------------------


async def test_scope_work_and_collection(
    client: httpx.AsyncClient,
    admin_database: Database,
    indexer: RecordingIndexer,
    access_store: ObjectStore,
    settings: Settings,
    book: Work,
    auth: Headers,
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        other = await make_work(session, title_ar="كتاب آخر عن الكرم", pages=1)
        published = await catalog.create_collection(
            session,
            settings,
            kind="thematic",
            title_ar="الزراعة",
            title_en=None,
            description_ar=None,
            description_en=None,
            publish=True,
        )
        await catalog.add_to_collection(session, published, other)
        draft = await catalog.create_collection(
            session,
            settings,
            kind="thematic",
            title_ar="مسودة",
            title_en=None,
            description_ar=None,
            description_en=None,
            publish=False,
        )
        await catalog.add_to_collection(session, draft, book)
    await _index_work(admin_database, indexer, access_store, settings, other, {1: "الكرم"})

    everything = (await client.get("/search", params={"q": "الكرم"})).json()
    assert everything["scope"] == "catalog"
    assert everything["total_works"] == 2

    in_work = (await client.get("/search", params={"q": "الكرم", "work": book.public_id})).json()
    assert in_work["scope"] == "work"
    assert [w["work"]["public_id"] for w in in_work["works"]] == [book.public_id]

    in_collection = (
        await client.get("/search", params={"q": "الكرم", "collection": published.public_id})
    ).json()
    assert in_collection["scope"] == "collection"
    assert [w["work"]["public_id"] for w in in_collection["works"]] == [other.public_id]

    hidden = await client.get("/search", params={"q": "الكرم", "collection": draft.public_id})
    assert hidden.status_code == 404
    staff = await client.get(
        "/search",
        params={"q": "الكرم", "collection": draft.public_id},
        headers=auth("carol", ["curator"], mfa=True),
    )
    assert staff.status_code == 200
    assert staff.json()["total_works"] == 1

    unknown = await client.get("/search", params={"q": "الكرم", "work": "w8nothere"})
    assert unknown.status_code == 404
    malformed = await client.get("/search", params={"q": "الكرم", "work": "../etc"})
    assert malformed.status_code == 422


# --- SRCH-2: query expansion from the vocabulary ----------------------------------------------


async def test_srch_2_vocabulary_expands_the_query_in_both_directions(
    client: httpx.AsyncClient,
    admin_database: Database,
    indexer: RecordingIndexer,
    access_store: ObjectStore,
    settings: Settings,
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, title_ar="أحوال السلط", title_en=None, pages=1)
        term = await catalog.upsert_term(
            session,
            scheme="gazetteer_jo",
            facet="place",
            code="salt",
            label_ar="السَّلْط",
            label_en="Al-Salt",
        )
        term.alt_labels = {"en": ["Es-Salt"], "ar": ["مدينة السلط (الأردن)"]}
        await catalog.link_term(session, work, term)
    await _index_work(admin_database, indexer, access_store, settings, work, {1: "ذكر السلط"})

    english = (await client.get("/search", params={"q": "Es-Salt"})).json()
    assert "السَّلْط" in english["expanded_terms"]
    assert english["total_works"] == 1
    arabic = (await client.get("/search", params={"q": "السلط"})).json()
    assert "Al-Salt" in arabic["expanded_terms"]
    assert "Es-Salt" in arabic["expanded_terms"]
    unrelated = (await client.get("/search", params={"q": "عمان"})).json()
    assert unrelated["expanded_terms"] == []


async def test_srch_2_agent_names_expand_across_scripts(
    client: httpx.AsyncClient, book: Work
) -> None:
    body = (await client.get("/search", params={"q": "Yaqub ibn Salim al-Tahhan"})).json()
    assert body["expanded_terms"] == ["يعقوب بن سالم الطحّان"]
    assert body["total_works"] == 1


# --- Pagination and caching ---------------------------------------------------------------------


async def test_pagination_and_pages_per_work(
    client: httpx.AsyncClient,
    admin_database: Database,
    indexer: RecordingIndexer,
    access_store: ObjectStore,
    settings: Settings,
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        works = [await make_work(session, title_ar=f"مخطوطة {n}", pages=4) for n in range(3)]
    for work in works:
        await _index_work(
            admin_database,
            indexer,
            access_store,
            settings,
            work,
            dict.fromkeys(range(1, 5), "مخطوطة"),
        )
    first = (
        await client.get("/search", params={"q": "مخطوطة", "limit": 2, "pages_per_work": 1})
    ).json()
    assert first["total_works"] == 3
    assert len(first["works"]) == 2
    assert all(len(w["pages"]) == 1 and w["page_hits_total"] == 4 for w in first["works"])
    second = (await client.get("/search", params={"q": "مخطوطة", "limit": 2, "offset": 2})).json()
    assert len(second["works"]) == 1
    seen = {w["work"]["public_id"] for w in first["works"]} | {
        w["work"]["public_id"] for w in second["works"]
    }
    assert seen == {w.public_id for w in works}


async def test_anonymous_results_are_cacheable_and_signed_in_results_are_not(
    client: httpx.AsyncClient, book: Work, auth: Headers
) -> None:
    anonymous = await client.get("/search", params={"q": "الكرم"})
    assert anonymous.headers["cache-control"].startswith("public")
    member = await client.get("/search", params={"q": "الكرم"}, headers=auth("m"))
    assert member.headers["cache-control"] == "private, no-store"


# --- SRCH-4: scan_visible agrees with the policy engine ----------------------------------------


def _principal(kind: str) -> Principal:
    if kind == "anonymous":
        return Principal.anonymous()
    roles = {"member": {"member"}, "curator": {"curator"}, "admin": {"platform_admin"}}[kind]
    return Principal(
        id=f"{kind}-1", roles=frozenset(roles), authenticated=True, user_id=uuid.uuid4(), mfa=True
    )


@pytest.mark.parametrize("access_class", list(AccessClass))
@pytest.mark.parametrize("publish_state", [PublishState.PUBLISHED, PublishState.DRAFT])
@pytest.mark.parametrize("frozen", [False, True])
@pytest.mark.parametrize("who", ["anonymous", "member", "curator", "admin"])
@pytest.mark.parametrize("with_grant", [False, True])
@pytest.mark.parametrize("seq", [1, 11])
async def test_srch_4_scan_visible_agrees_with_the_policy(
    settings: Settings,
    access_class: AccessClass,
    publish_state: PublishState,
    frozen: bool,
    who: str,
    with_grant: bool,
    seq: int,
) -> None:
    principal = _principal(who)
    if with_grant and who == "anonymous":
        pytest.skip("grants belong to signed-in users")
    work = Work(
        id=uuid.uuid4(),
        public_id="w8test",
        title_ar="t",
        access_class=access_class,
        publish_state=publish_state,
        frozen=frozen,
    )
    grant = (
        Grant(work_id=work.id, user_id=principal.user_id, page_from=1, page_to=5)
        if with_grant
        else None
    )
    policy = CerbosPolicyClient(settings)
    ref = ResourceRef(
        kind="page", id="w8test-p0001", attr=catalog.page_attributes(work, seq, grant)
    )
    expected = await policy.is_allowed(principal, "read", ref, None)
    assert scan_visible(work, seq, grant, principal) is expected


# --- Backend unit tests -------------------------------------------------------------------------


def test_normalize_and_tokens() -> None:
    assert search_backend.normalize("الكَرْمُ") == "الكرم"
    assert search_backend.normalize("أإآ ة ى") == "ااا ه ي"  # noqa: RUF001
    assert search_backend.tokens("Wadi al-Karm، وادي الكَرْم") == [
        "wadi",
        "al",
        "karm",
        "وادي",
        "الكرم",
    ]
    normalized, positions = search_backend.normalize_with_map("كَرْم")
    assert normalized == "كرم"
    assert positions == [0, 2, 4]


def test_rrf_rewards_agreement() -> None:
    fused = search_backend.rrf(["a", "b", "c"], ["b", "a"], ["b"])
    assert sorted(fused, key=fused.get, reverse=True) == ["b", "a", "c"]  # type: ignore[arg-type]


def test_opensearch_queries_always_carry_the_visibility_filters() -> None:
    public = Filters(subjects=("x",), work_public_ids=("w1",))
    works = works_query("الكرم", public, limit=10)
    pages = pages_query("الكرم", public, limit=10)
    for body, pages_flag in ((works, False), (pages, True)):
        clauses = body["query"]["bool"]["filter"]
        assert {"term": {"publish_state": "published"}} in clauses
        assert {"term": {"frozen": False}} in clauses
        assert {"bool": {"must_not": {"term": {"access_class": "embargoed"}}}} in clauses
        field = "work_public_id" if pages_flag else "public_id"
        assert {"terms": {field: ["w1"]}} in clauses
    assert {"terms": {"subjects": ["x"]}} in works["query"]["bool"]["filter"]
    assert works["_source"] == ["public_id"]
    assert pages["_source"] == ["work_public_id", "seq"]
    assert "highlight" not in works
    assert "highlight" not in pages
    staff = Filters(published_only=False, exclude_embargoed=False, exclude_frozen=False)
    assert works_query("x", staff, limit=1)["query"]["bool"]["filter"] == []


async def test_route_coverage_includes_search(app: FastAPI) -> None:
    from tests.core.test_route_coverage import _has_authorize, api_routes

    routes = {route.path: route for route in api_routes(app)}
    assert "/search" in routes
    assert _has_authorize(routes["/search"].dependant)
