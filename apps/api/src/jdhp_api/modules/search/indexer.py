"""Search indexing: page and work documents for OpenSearch (CAT-4, SRCH-1).

Page text is indexed for matching but excluded from ``_source`` by the index template, so
nothing that reads the index can get the text back; highlights come from ALTO offsets.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from typing import Any, Protocol

from opensearchpy import OpenSearch

from jdhp_api.core.config import Settings


@dataclass(frozen=True, slots=True)
class PageDocument:
    page_id: uuid.UUID
    work_id: uuid.UUID
    work_public_id: str
    seq: int
    label: str | None
    text: str
    language: str
    access_class: str
    publish_state: str
    frozen: bool

    def body(self) -> dict[str, Any]:
        data = asdict(self)
        data["page_id"] = str(self.page_id)
        data["work_id"] = str(self.work_id)
        return data


@dataclass(frozen=True, slots=True)
class WorkDocument:
    work_id: uuid.UUID
    public_id: str
    title_ar: str
    title_translit: str | None
    title_en: str | None
    description_ar: str | None
    description_en: str | None
    agents: list[str]
    subjects: list[str]
    places: list[str]
    periods: list[str]
    language: str
    date_earliest: str | None
    date_latest: str | None
    access_class: str
    publish_state: str
    frozen: bool

    def body(self) -> dict[str, Any]:
        data = asdict(self)
        data["work_id"] = str(self.work_id)
        return data


class SearchIndexer(Protocol):
    def index_page(self, document: PageDocument) -> None: ...

    def index_work(self, document: WorkDocument) -> None: ...

    def delete_page(self, page_id: uuid.UUID) -> None: ...


class OpenSearchIndexer:
    def __init__(self, settings: Settings) -> None:
        auth = None
        if settings.opensearch_user and settings.opensearch_password:
            auth = (settings.opensearch_user, settings.opensearch_password.get_secret_value())
        self._client = OpenSearch(hosts=[str(settings.opensearch_url)], http_auth=auth, timeout=10)
        self.pages_index = f"{settings.opensearch_index_prefix}-pages"
        self.works_index = f"{settings.opensearch_index_prefix}-works"

    def index_page(self, document: PageDocument) -> None:
        self._client.index(
            index=self.pages_index, id=str(document.page_id), body=document.body(), refresh=False
        )

    def index_work(self, document: WorkDocument) -> None:
        self._client.index(
            index=self.works_index, id=str(document.work_id), body=document.body(), refresh=False
        )

    def delete_page(self, page_id: uuid.UUID) -> None:
        self._client.delete(index=self.pages_index, id=str(page_id), ignore=[404])


class RecordingIndexer:
    """Collects documents instead of sending them. Tests read ``pages`` and ``works``."""

    def __init__(self) -> None:
        self.pages: list[PageDocument] = []
        self.works: list[WorkDocument] = []
        self.deleted: list[uuid.UUID] = []

    def index_page(self, document: PageDocument) -> None:
        self.pages.append(document)

    def index_work(self, document: WorkDocument) -> None:
        self.works.append(document)

    def delete_page(self, page_id: uuid.UUID) -> None:
        self.deleted.append(page_id)
