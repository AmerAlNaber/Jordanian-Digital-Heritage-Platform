"""The seed book through the real pipeline with the mock OCR provider (Phase 0 acceptance)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Row, func, select
from sqlalchemy.sql import Executable

from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.orm import DigitalObjectState, FixityStatus, IntakeState, PremisEventType
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.content.models import PageEmbedding
from jdhp_api.modules.ingest.models import DigitalObject, Incident, IntakeBatch, Page, PremisEvent
from jdhp_api.modules.search.indexer import RecordingIndexer
from jdhp_metadata.alto import from_alto_xml, plain_text
from jdhp_metadata.mets import parse_mets
from jdhp_worker import seed as seed_module
from jdhp_worker.inline import run_inline
from jdhp_worker.pipeline import fixity
from jdhp_worker.runtime import Runtime

JP2_SIGNATURE = b"\x00\x00\x00\x0cjP  \r\n\x87\n"


def _register(runtime: Runtime, app_database: Database, manifest: dict[str, object]) -> str:
    batch_code, _work = runtime.run(
        seed_module.register(app_database, runtime.settings, manifest, publish=True)
    )

    async def batch_id() -> str:
        from jdhp_api.modules.ingest import service

        async with runtime.database.session(RlsContext.system()) as session:
            batch = await service.get_batch_by_code(session, batch_code)
            assert batch is not None
            return str(batch.id)

    return runtime.run(batch_id())


def _fetch(database: Database, stmt: Executable) -> Sequence[Row[Any]]:
    async def go() -> Sequence[Row[Any]]:
        async with database.session(RlsContext.system()) as session:
            return (await session.execute(stmt)).all()

    return asyncio.run(go())


def test_seed_book_is_ingested_through_the_real_pipeline(
    runtime: Runtime,
    app_database: Database,
    admin_database: Database,
    seed_output: Path,
    indexer: RecordingIndexer,
) -> None:
    settings = runtime.settings
    manifest = seed_module.upload_seed(runtime, seed_output)
    batch_id = _register(runtime, app_database, manifest)
    results = run_inline(runtime, "jdhp.ingest.package", batch_id=batch_id)
    assert results[0]["status"] == "packaged"
    assert len(results) == 1 + 40 * 3  # package, then derivatives + ocr + embeddings per page

    rows = _fetch(admin_database, select(Page).order_by(Page.seq))
    pages = [r[0] for r in rows]
    assert len(pages) == 40
    assert all(
        p.master_key and p.derivative_key and p.thumb_key and p.alto_key and p.offsets_key
        for p in pages
    )
    assert all(p.ocr_at is not None and p.width_px and p.height_px for p in pages)
    # Registered class: the first ten pages carry a public sample, the rest do not (CAT-1).
    assert [p.sample_key is not None for p in pages] == [True] * 10 + [False] * 30
    # The OCR text is the ground truth, internal to the page row.
    page7 = pages[6]
    assert "وادي الكَرْم" in (page7.ocr_text or "")
    assert pages[24].ocr_flagged is True, (
        "page 25 is rendered under the 85 percent confidence threshold"
    )
    assert pages[6].ocr_flagged is False

    (digital_object,) = [r[0] for r in _fetch(admin_database, select(DigitalObject))]
    assert digital_object.state == DigitalObjectState.READY
    assert digital_object.fixity_status == FixityStatus.OK
    assert digital_object.mets_key is not None
    (batch,) = [r[0] for r in _fetch(admin_database, select(IntakeBatch))]
    assert batch.state == IntakeState.INGESTED

    # Preservation holds masters, METS and the checksum manifest; access holds derivatives.
    mets = parse_mets(
        runtime.ingest_store.get(settings.bucket_preservation, digital_object.mets_key)
    )
    assert len(mets.files) == 40
    assert mets.files[0].sha256 == pages[0].master_sha256
    checksums = runtime.ingest_store.get(
        settings.bucket_preservation,
        f"{digital_object.work_id}/{digital_object.id}/checksums.sha256",
    )
    assert checksums.decode().count("\n") == 40
    derivative = runtime.store.get(settings.bucket_access, pages[0].derivative_key)
    assert derivative.startswith(JP2_SIGNATURE)
    alto = from_alto_xml(runtime.store.get(settings.bucket_access, page7.alto_key))
    assert plain_text(alto) == page7.ocr_text
    offsets = json.loads(runtime.store.get(settings.bucket_access, page7.offsets_key))
    assert offsets
    assert {"start", "end", "x", "y", "w", "h"} <= set(offsets[0])

    # Search documents and embeddings carry model and version (SRCH-6).
    assert len(indexer.pages) == 40
    assert indexer.works
    assert indexer.works[0].agents
    (count,) = _fetch(admin_database, select(func.count()).select_from(PageEmbedding))[0]
    assert count >= 40
    (sample_embedding,) = [r[0] for r in _fetch(admin_database, select(PageEmbedding).limit(1))]
    assert sample_embedding.model == "mock-embeddings"
    assert sample_embedding.dimensions == 16

    events = [r[0] for r in _fetch(admin_database, select(PremisEvent))]
    kinds = {e.event_type for e in events}
    assert {PremisEventType.INGEST, PremisEventType.DERIVATIVE_GENERATION} <= kinds
    (work,) = [r[0] for r in _fetch(admin_database, select(Work))]
    assert work.publish_state.value == "published"


def test_sec_17_checksum_mismatch_fails_the_batch(
    runtime: Runtime, app_database: Database, admin_database: Database, seed_output: Path
) -> None:
    settings = runtime.settings
    manifest = seed_module.upload_seed(runtime, seed_output)
    manifest["pages"] = manifest["pages"][:3]  # type: ignore[index]
    # Tamper with the staged second page after the manifest was written.
    key = f"{seed_module.STAGING_PREFIX}/0002.tif"
    original = runtime.store.get(settings.bucket_uploads, key)
    runtime.store.put(
        settings.bucket_uploads, key, original[:-16] + b"\x00" * 16, content_type="image/tiff"
    )
    batch_id = _register(runtime, app_database, manifest)
    results = run_inline(runtime, "jdhp.ingest.package", batch_id=batch_id)
    assert results[0]["status"] == "failed"
    assert "checksum" in str(results[0]["reason"])
    (batch,) = [r[0] for r in _fetch(admin_database, select(IntakeBatch))]
    assert batch.state == IntakeState.FAILED
    assert batch.error_detail
    assert "page 2" in batch.error_detail
    # The first page's master was written; nothing after the failure was.
    assert len(list(runtime.ingest_store.list(settings.bucket_preservation, ""))) == 1


def test_sec_17_non_tiff_upload_is_rejected(
    runtime: Runtime, app_database: Database, admin_database: Database, seed_output: Path
) -> None:
    import hashlib

    settings = runtime.settings
    manifest = seed_module.upload_seed(runtime, seed_output)
    manifest["pages"] = manifest["pages"][:1]  # type: ignore[index]
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    runtime.store.put(settings.bucket_uploads, f"{seed_module.STAGING_PREFIX}/0001.tif", png)
    manifest["pages"][0]["sha256"] = hashlib.sha256(png).hexdigest()  # type: ignore[index]
    batch_id = _register(runtime, app_database, manifest)
    results = run_inline(runtime, "jdhp.ingest.package", batch_id=batch_id)
    assert results[0]["status"] == "failed"
    assert "magic bytes" in str(results[0]["reason"])


def test_fixity_mismatch_opens_incident_and_freezes_object(
    runtime: Runtime, app_database: Database, admin_database: Database, seed_output: Path
) -> None:
    settings = runtime.settings
    manifest = seed_module.upload_seed(runtime, seed_output)
    manifest["pages"] = manifest["pages"][:2]  # type: ignore[index]
    batch_id = _register(runtime, app_database, manifest)
    run_inline(runtime, "jdhp.ingest.package", batch_id=batch_id)
    (digital_object,) = [r[0] for r in _fetch(admin_database, select(DigitalObject))]
    assert runtime.run(fixity.verify_digital_object(runtime, digital_object.id))["mismatches"] == 0
    # Corrupt a master behind the platform's back (object lock would stop this in production).
    pages = [r[0] for r in _fetch(admin_database, select(Page).order_by(Page.seq))]
    runtime.ingest_store.put(settings.bucket_preservation, pages[1].master_key, b"II*\x00corrupted")
    result = runtime.run(fixity.verify_digital_object(runtime, digital_object.id))
    assert result["mismatches"] == 1
    (digital_object,) = [r[0] for r in _fetch(admin_database, select(DigitalObject))]
    assert digital_object.state == DigitalObjectState.FROZEN
    assert digital_object.fixity_status == FixityStatus.MISMATCH
    (work,) = [r[0] for r in _fetch(admin_database, select(Work))]
    assert work.frozen is True
    incidents = [r[0] for r in _fetch(admin_database, select(Incident))]
    assert len(incidents) == 1
    assert incidents[0].detail["mismatches"][0]["seq"] == 2


class _FailingStore:
    """Delegates to a real store but refuses writes whose key matches, like a failing disk."""

    def __init__(self, inner: Any, *, fails_when: Any) -> None:
        self._inner = inner
        self._fails_when = fails_when

    def put(self, bucket: str, key: str, data: bytes, **kwargs: Any) -> Any:
        if self._fails_when(key):
            msg = f"disk full writing {key}"
            raise RuntimeError(msg)
        return self._inner.put(bucket, key, data, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._inner, name)


class _BrokenOcr:
    info = None

    async def recognize(self, image: bytes, *, page_ref: str, language_hints: Any = ()) -> Any:
        msg = f"provider unavailable for {page_ref}"
        raise ConnectionError(msg)


def _failure_events(admin_database: Database) -> list[PremisEvent]:
    return [
        r[0]
        for r in _fetch(admin_database, select(PremisEvent).where(PremisEvent.outcome == "fail"))
    ]


def test_adm_1_derivative_failure_is_recorded_on_the_batch(
    runtime: Runtime, app_database: Database, admin_database: Database, seed_output: Path
) -> None:
    manifest = seed_module.upload_seed(runtime, seed_output)
    manifest["pages"] = manifest["pages"][:2]  # type: ignore[index]
    batch_id = _register(runtime, app_database, manifest)
    runtime.store = _FailingStore(runtime.store, fails_when=lambda key: "/jp2/" in key)  # type: ignore[assignment]
    with pytest.raises(RuntimeError, match="disk full"):
        run_inline(runtime, "jdhp.ingest.package", batch_id=batch_id)
    (batch,) = [r[0] for r in _fetch(admin_database, select(IntakeBatch))]
    assert batch.state == IntakeState.FAILED
    assert batch.error_detail is not None
    assert batch.error_detail.startswith("page 1 derivatives: RuntimeError: disk full")
    assert batch.completed_at is not None
    (event,) = _failure_events(admin_database)
    assert event.event_type == PremisEventType.DERIVATIVE_GENERATION
    assert event.detail["stage"] == "derivatives"
    assert event.page_id is not None


def test_adm_1_ocr_failure_is_recorded_on_the_batch(
    runtime: Runtime, app_database: Database, admin_database: Database, seed_output: Path
) -> None:
    manifest = seed_module.upload_seed(runtime, seed_output)
    manifest["pages"] = manifest["pages"][:1]  # type: ignore[index]
    batch_id = _register(runtime, app_database, manifest)
    runtime.ocr = _BrokenOcr()  # type: ignore[assignment]
    with pytest.raises(ConnectionError, match="provider unavailable"):
        run_inline(runtime, "jdhp.ingest.package", batch_id=batch_id)
    (batch,) = [r[0] for r in _fetch(admin_database, select(IntakeBatch))]
    assert batch.state == IntakeState.FAILED
    assert batch.error_detail == "page 1 ocr: ConnectionError: provider unavailable for 0001.tif"
    (event,) = _failure_events(admin_database)
    assert event.event_type == PremisEventType.INGEST
    assert event.detail == {
        "stage": "ocr",
        "reason": "ConnectionError: provider unavailable for 0001.tif",
    }


def test_adm_1_packaging_failure_is_recorded_on_the_batch(
    runtime: Runtime, app_database: Database, admin_database: Database, seed_output: Path
) -> None:
    manifest = seed_module.upload_seed(runtime, seed_output)
    manifest["pages"] = manifest["pages"][:1]  # type: ignore[index]
    batch_id = _register(runtime, app_database, manifest)
    runtime.ingest_store = _FailingStore(  # type: ignore[assignment]
        runtime.ingest_store, fails_when=lambda key: key.endswith("mets.xml")
    )
    with pytest.raises(RuntimeError, match="disk full"):
        run_inline(runtime, "jdhp.ingest.package", batch_id=batch_id)
    (batch,) = [r[0] for r in _fetch(admin_database, select(IntakeBatch))]
    assert batch.state == IntakeState.FAILED
    assert batch.error_detail is not None
    assert batch.error_detail.startswith("packaging: RuntimeError: disk full")
    (event,) = _failure_events(admin_database)
    assert event.page_id is None
    assert event.detail["stage"] == "packaging"
