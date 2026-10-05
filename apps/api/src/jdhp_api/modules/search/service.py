"""Unified search (SRCH-1 to SRCH-4, CAT-4, CAT-5).

The backend returns identifiers and scores. This service rechecks every hit against the
database under the caller's visibility, fuses the rankings of the query and of its vocabulary
expansions with reciprocal rank fusion, and turns matched character offsets into word boxes on
the scan. No text leaves this module: a page hit is a sequence number, a score and regions,
and regions are given only for pages whose scan the caller may see.
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import re
import uuid
from collections.abc import Iterable, Sequence
from typing import Any

from botocore.exceptions import BotoCoreError, ClientError
from sqlalchemy import Text, cast, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from jdhp_api.core.auth import Principal
from jdhp_api.core.config import Settings
from jdhp_api.core.errors import NotFoundError
from jdhp_api.core.ids import format_page_ark
from jdhp_api.core.orm import AccessClass, PublishState
from jdhp_api.core.storage import ObjectStore
from jdhp_api.modules.access.models import Grant
from jdhp_api.modules.access.service import active_grant_for, grant_covers_page
from jdhp_api.modules.catalog import service as catalog
from jdhp_api.modules.catalog.models import Agent, CollectionWork, VocabularyTerm, Work
from jdhp_api.modules.ingest.models import Page
from jdhp_api.modules.search.backend import (
    DIACRITICS,
    LETTER_MAP,
    Filters,
    PageHitRaw,
    SearchBackend,
    normalize,
    rrf,
)
from jdhp_api.modules.search.schemas import (
    FacetBucket,
    PageHit,
    Region,
    Scope,
    SearchResponse,
    WorkHit,
)

MAX_EXPANSIONS = 4
WORKS_FETCH = 200
PAGES_FETCH = 500
MAX_REGIONS_PER_PAGE = 40
MAX_PAGES_PER_WORK = 10
# Roles the page policy lets read every non-embargoed, non-frozen page without a grant.
READ_STAFF = frozenset({"curator", "reviewer", "rights_officer"})

_PARENTHETICAL = re.compile(r"\([^)]*\)")


@dataclasses.dataclass(frozen=True, slots=True)
class SearchRequest:
    q: str
    collection: str | None = None
    work: str | None = None
    subjects: tuple[str, ...] = ()
    places: tuple[str, ...] = ()
    periods: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    access_classes: tuple[str, ...] = ()
    limit: int = 20
    offset: int = 0
    pages_per_work: int = 3

    @property
    def scope(self) -> Scope:
        if self.work:
            return "work"
        if self.collection:
            return "collection"
        return "catalog"


# --- Visibility -------------------------------------------------------------------------------


def scan_visible(work: Work, seq: int, grant: Grant | None, principal: Principal) -> bool:
    """Whether the caller may see this page's scan, mirroring the ``read`` rules of the page
    policy. The tile gateway asks the policy engine for every tile; this flag only decides
    whether matched regions are included. ``test_srch_4_scan_visible_agrees_with_the_policy``
    proves the two agree."""
    if work.frozen or work.access_class == AccessClass.EMBARGOED:
        return False
    if principal.roles & READ_STAFF:
        return True
    if work.publish_state != PublishState.PUBLISHED:
        return False
    if catalog.in_sample_range(work, seq) or work.access_class == AccessClass.OPEN:
        return True
    if work.access_class == AccessClass.REGISTERED:
        return principal.authenticated
    return grant_covers_page(grant, seq)


def filters_for(
    principal: Principal, request: SearchRequest, work_ids: tuple[str, ...] | None
) -> Filters:
    """Staff search everything they can view; everyone else only published, open-to-view works."""
    public = not principal.is_staff
    return Filters(
        published_only=public,
        exclude_embargoed=public,
        exclude_frozen=public,
        work_public_ids=work_ids,
        access_classes=request.access_classes or None,
        subjects=request.subjects or None,
        places=request.places or None,
        periods=request.periods or None,
        languages=request.languages or None,
    )


async def scope_work_ids(
    session: AsyncSession, principal: Principal, request: SearchRequest
) -> tuple[str, ...] | None:
    """The works a scoped search may touch, or ``None`` for the whole catalog. A scope the
    caller may not see is reported as not found, like the catalog routes (CAT-5)."""
    if request.work:
        stmt = catalog.visible_works(select(Work.public_id), principal).where(
            Work.public_id == request.work
        )
        if (await session.scalars(stmt)).first() is None:
            raise NotFoundError
        return (request.work,)
    if request.collection:
        collection = await catalog.get_collection_by_name(session, request.collection)
        if collection is None or (
            collection.publish_state != PublishState.PUBLISHED and not principal.is_staff
        ):
            raise NotFoundError
        stmt = (
            catalog.visible_works(select(Work.public_id), principal)
            .join(CollectionWork, CollectionWork.work_id == Work.id)
            .where(CollectionWork.collection_id == collection.id)
        )
        return tuple(str(public_id) for public_id in (await session.scalars(stmt)).all())
    return None


# --- Query expansion from the controlled vocabulary and agents --------------------------------


def _folded(column: Any) -> ColumnElement[Any]:
    """The SQL twin of ``normalize``: lowercase, no marks, folded letters."""
    marks = "".join(sorted(DIACRITICS))
    letters_from = "".join(LETTER_MAP)
    letters_to = "".join(LETTER_MAP.values())
    return func.lower(func.translate(func.translate(column, marks, ""), letters_from, letters_to))


def label_key(label: str) -> str:
    """A label compared without its parenthetical qualifier, marks or case."""
    return " ".join(normalize(_PARENTHETICAL.sub(" ", label)).split())


def _flatten_labels(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _flatten_labels(item)
    elif isinstance(value, list):
        for item in value:
            yield from _flatten_labels(item)


async def expand_query(session: AsyncSession, q: str) -> list[str]:
    """Other names for what the query names: the paired label of a vocabulary term or agent
    whose label equals the query, and the term's alternative labels (SRCH-2)."""
    needle = label_key(q)
    if not needle:
        return []
    first_token = needle.split()[0]
    pattern = f"%{first_token}%"
    term_rows = await session.scalars(
        select(VocabularyTerm)
        .where(
            VocabularyTerm.deleted_at.is_(None),
            or_(
                _folded(VocabularyTerm.pref_label_ar).like(pattern),
                _folded(func.coalesce(VocabularyTerm.pref_label_en, "")).like(pattern),
                _folded(cast(VocabularyTerm.alt_labels, Text)).like(pattern),
            ),
        )
        .limit(50)
    )
    agent_rows = await session.scalars(
        select(Agent)
        .where(
            Agent.deleted_at.is_(None),
            or_(
                _folded(Agent.name_ar).like(pattern),
                _folded(func.coalesce(Agent.name_latin, "")).like(pattern),
            ),
        )
        .limit(50)
    )
    expansions: list[str] = []

    def consider(labels: Sequence[str]) -> None:
        keys = {label_key(label) for label in labels}
        if needle not in keys:
            return
        for label in labels:
            key = label_key(label)
            if key and key != needle and key not in {label_key(e) for e in expansions}:
                expansions.append(_PARENTHETICAL.sub("", label).strip())

    for term in term_rows.all():
        alternatives = [str(label) for label in _flatten_labels(term.alt_labels)]
        consider(
            [
                term.pref_label_ar,
                *([term.pref_label_en] if term.pref_label_en else []),
                *alternatives,
            ]
        )
    for agent in agent_rows.all():
        consider([agent.name_ar, *([agent.name_latin] if agent.name_latin else [])])
    return expansions[:MAX_EXPANSIONS]


# --- Regions ----------------------------------------------------------------------------------


def _load_offsets(store: ObjectStore, bucket: str, key: str) -> list[dict[str, int]]:
    try:
        data = json.loads(store.get(bucket, key))
    except (ClientError, BotoCoreError, ValueError):
        return []
    return [entry for entry in data if isinstance(entry, dict)] if isinstance(data, list) else []


def regions_from(
    offsets: Sequence[dict[str, int]], spans: Sequence[tuple[int, int]]
) -> list[Region]:
    """Word boxes whose character span overlaps a matched span, in reading order."""
    regions: list[Region] = []
    for entry in offsets:
        start, end = int(entry.get("start", -1)), int(entry.get("end", -1))
        if start < 0 or end < 0:
            continue
        if any(start < span_end and end > span_start for span_start, span_end in spans):
            regions.append(
                Region(x=int(entry["x"]), y=int(entry["y"]), w=int(entry["w"]), h=int(entry["h"]))
            )
            if len(regions) >= MAX_REGIONS_PER_PAGE:
                break
    return regions


# --- The search -------------------------------------------------------------------------------


async def search(
    session: AsyncSession,
    principal: Principal,
    settings: Settings,
    backend: SearchBackend,
    store: ObjectStore,
    request: SearchRequest,
) -> SearchResponse:
    work_ids = await scope_work_ids(session, principal, request)
    filters = filters_for(principal, request, work_ids)
    expansions = await expand_query(session, request.q)
    queries = [request.q, *expansions]

    if work_ids == ():
        return _empty(request, expansions)

    # Subject, place and period live on the work document. When the caller filters by them,
    # page hits are confined to the works that pass, so a page cannot bring back a work the
    # facet excluded.
    page_filters = filters
    if request.subjects or request.places or request.periods:
        passing = tuple(await backend.filter_works(filters, limit=WORKS_FETCH))
        if not passing:
            return _empty(request, expansions)
        page_filters = dataclasses.replace(filters, work_public_ids=passing)

    works_results = [
        await backend.search_works(query, filters, limit=WORKS_FETCH) for query in queries
    ]
    pages_results = [
        await backend.search_pages(query, page_filters, limit=PAGES_FETCH) for query in queries
    ]

    page_scores = rrf(*[[hit.page_id for hit in result.hits] for result in pages_results])
    page_hits: dict[str, PageHitRaw] = {}
    for result in pages_results:
        for hit in result.hits:
            page_hits.setdefault(hit.page_id, hit)
    fused_pages = sorted(page_hits.values(), key=lambda h: (-page_scores[h.page_id], h.seq))
    works_from_pages = list(dict.fromkeys(hit.work_public_id for hit in fused_pages))
    work_scores = rrf(
        *[[hit.public_id for hit in result.hits] for result in works_results], works_from_pages
    )
    candidates = sorted(work_scores, key=lambda public_id: (-work_scores[public_id], public_id))

    # Every hit is rechecked against the database under the caller's visibility (CAT-5).
    visible = catalog.visible_works(select(Work).where(Work.public_id.in_(candidates)), principal)
    by_public_id = {work.public_id: work for work in (await session.scalars(visible)).all()}
    ordered = [by_public_id[public_id] for public_id in candidates if public_id in by_public_id]

    pages_by_work: dict[str, list[PageHitRaw]] = {}
    for hit in fused_pages:
        if hit.work_public_id in by_public_id:
            pages_by_work.setdefault(hit.work_public_id, []).append(hit)

    window = ordered[request.offset : request.offset + request.limit]
    summaries = await catalog.summarize_many(session, window, settings)
    analyzed: set[str] = set()
    for query in queries:
        analyzed.update(await backend.analyze(query))

    work_hits: list[WorkHit] = []
    for work, summary in zip(window, summaries, strict=True):
        hits = pages_by_work.get(work.public_id, [])
        shown = hits[: request.pages_per_work]
        grant = await active_grant_for(session, user_id=principal.user_id, work_id=work.id)
        page_rows = await _pages_by_id(session, [hit.page_id for hit in shown])
        page_out: list[PageHit] = []
        visible_ids = [
            hit.page_id
            for hit in shown
            if hit.page_id in page_rows
            and scan_visible(work, page_rows[hit.page_id].seq, grant, principal)
        ]
        spans = await backend.term_offsets(visible_ids, sorted(analyzed)) if visible_ids else {}
        for hit in shown:
            page = page_rows.get(hit.page_id)
            if page is None:
                continue
            can_see = hit.page_id in visible_ids
            regions: list[Region] = []
            if can_see and page.offsets_key and spans.get(hit.page_id):
                offsets = await asyncio.to_thread(
                    _load_offsets, store, settings.bucket_access, page.offsets_key
                )
                regions = regions_from(offsets, spans[hit.page_id])
            page_out.append(
                PageHit(
                    seq=page.seq,
                    ark=format_page_ark(settings.ark_naan, work.public_id, page.seq),
                    label=page.label,
                    score=round(page_scores[hit.page_id], 6),
                    scan_visible=can_see,
                    thumbnail_available=page.thumb_key is not None,
                    regions=regions,
                )
            )
        work_hits.append(
            WorkHit(
                work=summary,
                score=round(work_scores[work.public_id], 6),
                pages=page_out,
                page_hits_total=len(hits),
            )
        )

    facets = {
        name: [FacetBucket(value=value, count=count) for value, count in buckets]
        for name, buckets in works_results[0].facets.items()
    }
    return SearchResponse(
        query=request.q,
        scope=request.scope,
        expanded_terms=expansions,
        total_works=len(ordered),
        total_page_hits=sum(len(hits) for hits in pages_by_work.values()),
        works=work_hits,
        facets=facets,
        limit=request.limit,
        offset=request.offset,
    )


def _empty(request: SearchRequest, expansions: list[str]) -> SearchResponse:
    return SearchResponse(
        query=request.q,
        scope=request.scope,
        expanded_terms=expansions,
        total_works=0,
        total_page_hits=0,
        works=[],
        facets={},
        limit=request.limit,
        offset=request.offset,
    )


async def _pages_by_id(session: AsyncSession, page_ids: Sequence[str]) -> dict[str, Page]:
    uuids: list[uuid.UUID] = []
    for page_id in page_ids:
        try:
            uuids.append(uuid.UUID(page_id))
        except ValueError:
            continue
    if not uuids:
        return {}
    rows = await session.scalars(select(Page).where(Page.id.in_(uuids)))
    return {str(page.id): page for page in rows.all()}
