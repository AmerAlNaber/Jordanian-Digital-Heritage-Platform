"""Search backends: OpenSearch in deployments, an in-memory twin for tests.

Both take the same structured filters, so the mandatory visibility filters are applied by the
backend before any aggregation (CAT-5), and both return hits as identifiers and scores only:
no backend ever hands text back to the service (CAT-4). Matched character offsets come from
term vectors, which OpenSearch keeps without the source text.
"""

from __future__ import annotations

import asyncio
import dataclasses
import re
from collections import Counter
from collections.abc import Iterable, Sequence
from typing import Any, Protocol

from opensearchpy import OpenSearch

from jdhp_api.core.config import Settings
from jdhp_api.modules.search.indexer import PageDocument, RecordingIndexer, WorkDocument

WORK_FIELDS = [
    "title_ar^5",
    "title_ar.exact^6",
    "title_en^5",
    "title_translit^5",
    "agents^3",
    "subjects^3",
    "places^3",
    "periods^2",
    "description_ar^2",
    "description_en^2",
]
FACET_FIELDS = ("subjects", "places", "periods", "language", "access_class")
ANALYZER = "arabic_heritage"
MAX_TERM_HITS = 500
RRF_K = 60

DIACRITICS = set("ًٌٍَُِّْٰـ") | {chr(c) for c in range(0x06D6, 0x06EE)}
LETTER_MAP = {"أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا", "ة": "ه", "ى": "ي", "ؤ": "و", "ئ": "ي"}  # noqa: RUF001
# Letters and digits in any script. Arabic punctuation and combining marks are not word
# characters, so they end a token the way Latin punctuation does.
_TOKEN = re.compile(r"\w+", re.UNICODE)


@dataclasses.dataclass(frozen=True, slots=True)
class Filters:
    """What every query is narrowed by. ``None`` means no restriction on that dimension."""

    published_only: bool = True
    exclude_embargoed: bool = True
    exclude_frozen: bool = True
    work_public_ids: tuple[str, ...] | None = None
    access_classes: tuple[str, ...] | None = None
    subjects: tuple[str, ...] | None = None
    places: tuple[str, ...] | None = None
    periods: tuple[str, ...] | None = None
    languages: tuple[str, ...] | None = None


@dataclasses.dataclass(frozen=True, slots=True)
class WorkHitRaw:
    public_id: str
    score: float


@dataclasses.dataclass(frozen=True, slots=True)
class PageHitRaw:
    page_id: str
    work_public_id: str
    seq: int
    score: float


@dataclasses.dataclass(frozen=True, slots=True)
class WorksResult:
    hits: list[WorkHitRaw]
    total: int
    facets: dict[str, list[tuple[str, int]]]


@dataclasses.dataclass(frozen=True, slots=True)
class PagesResult:
    hits: list[PageHitRaw]
    total: int


class SearchBackend(Protocol):
    async def analyze(self, text: str) -> list[str]: ...

    async def filter_works(self, filters: Filters, *, limit: int) -> list[str]: ...

    async def search_works(self, query: str, filters: Filters, *, limit: int) -> WorksResult: ...

    async def search_pages(self, query: str, filters: Filters, *, limit: int) -> PagesResult: ...

    async def term_offsets(
        self, page_ids: Sequence[str], terms: Sequence[str]
    ) -> dict[str, list[tuple[int, int]]]: ...


# --- Normalization shared by the in-memory twin (mirrors the index template) ----------------


def normalize_with_map(text: str) -> tuple[str, list[int]]:
    """Lowercase, drop diacritics and tatweel, fold letters; keep a map to original offsets."""
    out: list[str] = []
    positions: list[int] = []
    for index, char in enumerate(text):
        if char in DIACRITICS:
            continue
        out.append(LETTER_MAP.get(char, char.lower()))
        positions.append(index)
    return "".join(out), positions


def normalize(text: str) -> str:
    return normalize_with_map(text)[0]


def tokens(text: str) -> list[str]:
    return [m.group(0) for m in _TOKEN.finditer(normalize(text))]


def rrf(*rankings: Iterable[str], k: int = RRF_K) -> dict[str, float]:
    """Reciprocal rank fusion over ranked lists of identifiers."""
    fused: dict[str, float] = {}
    for ranking in rankings:
        for rank, identifier in enumerate(ranking, start=1):
            fused[identifier] = fused.get(identifier, 0.0) + 1.0 / (k + rank)
    return fused


# --- OpenSearch -----------------------------------------------------------------------------


def _filter_clauses(filters: Filters, *, pages: bool) -> list[dict[str, Any]]:
    clauses: list[dict[str, Any]] = []
    if filters.published_only:
        clauses.append({"term": {"publish_state": "published"}})
    if filters.exclude_frozen:
        clauses.append({"term": {"frozen": False}})
    if filters.exclude_embargoed:
        clauses.append({"bool": {"must_not": {"term": {"access_class": "embargoed"}}}})
    if filters.work_public_ids is not None:
        field = "work_public_id" if pages else "public_id"
        clauses.append({"terms": {field: list(filters.work_public_ids)}})
    if filters.access_classes:
        clauses.append({"terms": {"access_class": list(filters.access_classes)}})
    if filters.languages:
        clauses.append({"terms": {"language": list(filters.languages)}})
    if not pages:
        for name, values in (
            ("subjects", filters.subjects),
            ("places", filters.places),
            ("periods", filters.periods),
        ):
            if values:
                clauses.append({"terms": {name: list(values)}})
    return clauses


def works_query(query: str, filters: Filters, *, limit: int) -> dict[str, Any]:
    return {
        "size": limit,
        "_source": ["public_id"],
        "query": {
            "bool": {
                "must": {
                    "multi_match": {
                        "query": query,
                        "fields": WORK_FIELDS,
                        "type": "best_fields",
                        "operator": "or",
                        "minimum_should_match": "75%",
                    }
                },
                "filter": _filter_clauses(filters, pages=False),
            }
        },
        "aggs": {name: {"terms": {"field": name, "size": 50}} for name in FACET_FIELDS},
    }


def pages_query(query: str, filters: Filters, *, limit: int) -> dict[str, Any]:
    return {
        "size": limit,
        "_source": ["work_public_id", "seq"],
        "query": {
            "bool": {
                "must": {
                    "bool": {
                        "should": [
                            {"match": {"text": {"query": query, "minimum_should_match": "75%"}}},
                            {"match_phrase": {"text.exact": {"query": query, "boost": 2.0}}},
                        ],
                        "minimum_should_match": 1,
                    }
                },
                "filter": _filter_clauses(filters, pages=True),
            }
        },
    }


class OpenSearchBackend:
    def __init__(self, settings: Settings, client: OpenSearch | None = None) -> None:
        auth = None
        if settings.opensearch_user and settings.opensearch_password:
            auth = (settings.opensearch_user, settings.opensearch_password.get_secret_value())
        self._client = client or OpenSearch(
            hosts=[str(settings.opensearch_url)], http_auth=auth, timeout=10
        )
        self.pages_index = f"{settings.opensearch_index_prefix}-pages"
        self.works_index = f"{settings.opensearch_index_prefix}-works"

    async def analyze(self, text: str) -> list[str]:
        response = await asyncio.to_thread(
            self._client.indices.analyze,
            index=self.pages_index,
            body={"analyzer": ANALYZER, "text": text},
        )
        return [str(token["token"]) for token in response.get("tokens", [])]

    async def filter_works(self, filters: Filters, *, limit: int) -> list[str]:
        body = {
            "size": limit,
            "_source": ["public_id"],
            "query": {"bool": {"filter": _filter_clauses(filters, pages=False)}},
        }
        response = await asyncio.to_thread(self._client.search, index=self.works_index, body=body)
        return [str(h["_source"]["public_id"]) for h in response["hits"]["hits"]]

    async def search_works(self, query: str, filters: Filters, *, limit: int) -> WorksResult:
        response = await asyncio.to_thread(
            self._client.search,
            index=self.works_index,
            body=works_query(query, filters, limit=limit),
        )
        hits = [
            WorkHitRaw(public_id=str(h["_source"]["public_id"]), score=float(h["_score"] or 0.0))
            for h in response["hits"]["hits"]
        ]
        facets = {
            name: [(str(b["key"]), int(b["doc_count"])) for b in agg.get("buckets", [])]
            for name, agg in response.get("aggregations", {}).items()
        }
        return WorksResult(hits=hits, total=int(response["hits"]["total"]["value"]), facets=facets)

    async def search_pages(self, query: str, filters: Filters, *, limit: int) -> PagesResult:
        response = await asyncio.to_thread(
            self._client.search,
            index=self.pages_index,
            body=pages_query(query, filters, limit=limit),
        )
        hits = [
            PageHitRaw(
                page_id=str(h["_id"]),
                work_public_id=str(h["_source"]["work_public_id"]),
                seq=int(h["_source"]["seq"]),
                score=float(h["_score"] or 0.0),
            )
            for h in response["hits"]["hits"]
        ]
        return PagesResult(hits=hits, total=int(response["hits"]["total"]["value"]))

    async def term_offsets(
        self, page_ids: Sequence[str], terms: Sequence[str]
    ) -> dict[str, list[tuple[int, int]]]:
        if not page_ids or not terms:
            return {}
        wanted = set(terms)
        body = {
            "docs": [
                {
                    "_id": page_id,
                    "fields": ["text"],
                    "offsets": True,
                    "positions": False,
                    "payloads": False,
                    "term_statistics": False,
                    "field_statistics": False,
                }
                for page_id in page_ids
            ]
        }
        response = await asyncio.to_thread(
            self._client.mtermvectors, index=self.pages_index, body=body
        )
        offsets: dict[str, list[tuple[int, int]]] = {}
        for doc in response.get("docs", []):
            found: list[tuple[int, int]] = []
            vectors = doc.get("term_vectors", {}).get("text", {}).get("terms", {})
            for term, data in vectors.items():
                if term in wanted:
                    found.extend(
                        (int(t["start_offset"]), int(t["end_offset"]))
                        for t in data.get("tokens", [])
                    )
            offsets[str(doc["_id"])] = sorted(found)[:MAX_TERM_HITS]
        return offsets


# --- In-memory twin for tests ----------------------------------------------------------------


class InMemoryBackend:
    """Searches the documents a ``RecordingIndexer`` collected, with the same normalization."""

    def __init__(self, indexer: RecordingIndexer) -> None:
        self._indexer = indexer

    def _works(self) -> list[WorkDocument]:
        latest: dict[str, WorkDocument] = {}
        for doc in self._indexer.works:
            latest[doc.public_id] = doc
        return list(latest.values())

    def _pages(self) -> list[PageDocument]:
        latest: dict[str, PageDocument] = {}
        for doc in self._indexer.pages:
            latest[str(doc.page_id)] = doc
        return list(latest.values())

    @staticmethod
    def _passes(doc: WorkDocument | PageDocument, filters: Filters) -> bool:  # noqa: PLR0911
        if filters.published_only and doc.publish_state != "published":
            return False
        if filters.exclude_embargoed and doc.access_class == "embargoed":
            return False
        if filters.exclude_frozen and doc.frozen:
            return False
        public_id = doc.public_id if isinstance(doc, WorkDocument) else doc.work_public_id
        if filters.work_public_ids is not None and public_id not in filters.work_public_ids:
            return False
        if filters.access_classes and doc.access_class not in filters.access_classes:
            return False
        if filters.languages and doc.language not in filters.languages:
            return False
        if isinstance(doc, WorkDocument):
            for values, field in (
                (filters.subjects, doc.subjects),
                (filters.places, doc.places),
                (filters.periods, doc.periods),
            ):
                if values and not set(values) & set(field):
                    return False
        return True

    async def analyze(self, text: str) -> list[str]:
        return tokens(text)

    async def filter_works(self, filters: Filters, *, limit: int) -> list[str]:
        return sorted(d.public_id for d in self._works() if self._passes(d, filters))[:limit]

    async def search_works(self, query: str, filters: Filters, *, limit: int) -> WorksResult:
        terms = set(tokens(query))
        scored: list[WorkHitRaw] = []
        candidates = [d for d in self._works() if self._passes(d, filters)]
        for doc in candidates:
            weights = {
                5: [doc.title_ar, doc.title_en or "", doc.title_translit or ""],
                3: [*doc.agents, *doc.subjects, *doc.places],
                2: [*doc.periods, doc.description_ar or "", doc.description_en or ""],
            }
            score = 0.0
            for weight, fields in weights.items():
                field_tokens = set(tokens(" ".join(fields)))
                score += weight * len(terms & field_tokens)
            if score > 0:
                scored.append(WorkHitRaw(public_id=doc.public_id, score=score))
        scored.sort(key=lambda h: (-h.score, h.public_id))
        matched = {h.public_id for h in scored}
        facets: dict[str, list[tuple[str, int]]] = {}
        for name in FACET_FIELDS:
            counter: Counter[str] = Counter()
            for doc in candidates:
                if doc.public_id not in matched:
                    continue
                value = getattr(doc, name)
                for item in value if isinstance(value, list) else [value]:
                    counter[str(item)] += 1
            facets[name] = counter.most_common(50)
        return WorksResult(hits=scored[:limit], total=len(scored), facets=facets)

    async def search_pages(self, query: str, filters: Filters, *, limit: int) -> PagesResult:
        terms = set(tokens(query))
        scored: list[PageHitRaw] = []
        for doc in self._pages():
            if not self._passes(doc, filters):
                continue
            counts = Counter(tokens(doc.text))
            score = float(sum(counts[t] for t in terms))
            if score > 0:
                scored.append(
                    PageHitRaw(
                        page_id=str(doc.page_id),
                        work_public_id=doc.work_public_id,
                        seq=doc.seq,
                        score=score,
                    )
                )
        scored.sort(key=lambda h: (-h.score, h.work_public_id, h.seq))
        return PagesResult(hits=scored[:limit], total=len(scored))

    async def term_offsets(
        self, page_ids: Sequence[str], terms: Sequence[str]
    ) -> dict[str, list[tuple[int, int]]]:
        wanted = set(terms)
        by_id = {str(d.page_id): d for d in self._pages()}
        result: dict[str, list[tuple[int, int]]] = {}
        for page_id in page_ids:
            doc = by_id.get(page_id)
            if doc is None:
                continue
            normalized, positions = normalize_with_map(doc.text)
            found: list[tuple[int, int]] = []
            for match in _TOKEN.finditer(normalized):
                if match.group(0) in wanted:
                    start = positions[match.start()]
                    end = positions[match.end() - 1] + 1
                    found.append((start, end))
            result[page_id] = found[:MAX_TERM_HITS]
        return result
