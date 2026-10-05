"""Process-wide resources for tasks: database, object stores, providers, indexer.

Tasks are synchronous Celery callables; the services they call are async. ``Runtime.run``
executes a coroutine on a dedicated event loop thread so one engine serves the whole worker
process. Tests build a Runtime with mock providers and run coroutines inline.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from typing import Any, TypeVar

from jdhp_adapters.base import EmbeddingProvider, OcrProvider
from jdhp_adapters.mock.ocr import MockOcr
from jdhp_adapters.registry import make_embedding_provider, make_ocr_provider
from jdhp_api.core.db import Database
from jdhp_api.core.storage import ObjectStore, app_store
from jdhp_api.modules.search.indexer import OpenSearchIndexer, RecordingIndexer, SearchIndexer
from jdhp_worker.settings import WorkerSettings, get_worker_settings

T = TypeVar("T")


class LoopThread:
    """One event loop on one thread for the lifetime of the process."""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self.loop.run_forever, name="jdhp-worker-loop", daemon=True
        )
        self._thread.start()

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result()


@dataclass
class Runtime:
    settings: WorkerSettings
    database: Database
    store: ObjectStore
    ingest_store: ObjectStore
    ocr: OcrProvider
    embeddings: EmbeddingProvider
    indexer: SearchIndexer
    ground_truth_factory: Callable[[str], Callable[[str], dict[str, Any] | None]] | None = None
    loop: LoopThread | None = None
    enqueue: Callable[[str, dict[str, Any]], None] | None = None
    extras: dict[str, Any] = field(default_factory=dict)

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        if self.loop is not None:
            return self.loop.run(coro)
        return asyncio.run(coro)

    def send(self, task_name: str, **kwargs: Any) -> None:
        """Enqueue a follow-up task; tests capture these instead of using the broker."""
        if self.enqueue is not None:
            self.enqueue(task_name, kwargs)
            return
        from jdhp_worker.celery_app import app, configure

        configure(self.settings)

        app.send_task(task_name, kwargs=kwargs)

    def ocr_for(self, staging_prefix: str | None) -> OcrProvider:
        """The mock provider reads ground truth from the batch's staging prefix when it has one."""
        if (
            isinstance(self.ocr, MockOcr)
            and self.ground_truth_factory is not None
            and staging_prefix
        ):
            return MockOcr(self.ground_truth_factory(staging_prefix))
        return self.ocr


def ground_truth_from_store(
    store: ObjectStore, bucket: str
) -> Callable[[str], Callable[[str], dict[str, Any] | None]]:
    """Mock OCR ground truth sits beside the staged masters under ``ground_truth/<stem>.json``."""
    import json
    from pathlib import Path

    def factory(staging_prefix: str) -> Callable[[str], dict[str, Any] | None]:
        def lookup(page_ref: str) -> dict[str, Any] | None:
            key = f"{staging_prefix}/ground_truth/{Path(page_ref).stem}.json"
            if not store.exists(bucket, key):
                return None
            data = json.loads(store.get(bucket, key).decode("utf-8"))
            return data if isinstance(data, dict) else None

        return lookup

    return factory


def build_runtime(settings: WorkerSettings | None = None, *, loop: bool = True) -> Runtime:
    settings = settings or get_worker_settings()
    database = Database(settings.worker_sqlalchemy_url, pooled=loop)
    store = app_store(settings)
    if settings.has_ingest_credential:
        assert settings.s3_ingest_access_key is not None  # noqa: S101 - guarded by has_ingest_credential
        assert settings.s3_ingest_secret_key is not None  # noqa: S101
        ingest_store = ObjectStore(
            endpoint_url=str(settings.s3_endpoint_url) if settings.s3_endpoint_url else None,
            region=settings.s3_region,
            access_key=settings.s3_ingest_access_key.get_secret_value(),
            secret_key=settings.s3_ingest_secret_key.get_secret_value(),
            force_path_style=settings.s3_force_path_style,
        )
    else:
        ingest_store = store
    indexer: SearchIndexer
    try:
        indexer = OpenSearchIndexer(settings)
    except Exception:
        indexer = RecordingIndexer()
    return Runtime(
        settings=settings,
        database=database,
        store=store,
        ingest_store=ingest_store,
        ocr=make_ocr_provider(settings.ocr_provider),
        embeddings=make_embedding_provider(
            settings.embedding_provider, dimensions=settings.embedding_dimensions
        ),
        indexer=indexer,
        ground_truth_factory=ground_truth_from_store(store, settings.bucket_uploads),
        loop=LoopThread() if loop else None,
    )


_current: Runtime | None = None


def current() -> Runtime:
    global _current  # noqa: PLW0603 - process singleton
    if _current is None:
        _current = build_runtime()
    return _current


def set_current(runtime: Runtime | None) -> None:
    global _current  # noqa: PLW0603 - tests install their own runtime
    _current = runtime
