"""OCR: run the provider, keep ALTO and offsets for highlights, index the text, embed."""

from __future__ import annotations

import json
import uuid

from sqlalchemy import select

from jdhp_api.core import storage
from jdhp_api.core.db import RlsContext
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.ingest import service as ingest_service
from jdhp_api.modules.ingest.models import IntakeBatch, Page
from jdhp_api.modules.search.indexer import PageDocument
from jdhp_metadata.alto import offsets_map, to_alto_xml
from jdhp_worker.pipeline.finalize import maybe_finalize
from jdhp_worker.runtime import Runtime


async def recognize_page(rt: Runtime, page_id: uuid.UUID) -> dict[str, object]:
    settings = rt.settings
    async with rt.database.session(RlsContext.system()) as session:
        page = await session.get(Page, page_id)
        if page is None or page.master_key is None:
            return {"page": str(page_id), "status": "missing"}
        work = await session.get(Work, page.work_id)
        if work is None:
            return {"page": str(page_id), "status": "missing"}
        batch = (
            await session.scalars(
                select(IntakeBatch).where(IntakeBatch.digital_object_id == page.digital_object_id)
            )
        ).first()
        staging_prefix = batch.staging_prefix if batch else None
        seq, work_id, do_id, master_key = (
            page.seq,
            page.work_id,
            page.digital_object_id,
            page.master_key,
        )
        language = page.language or work.language
        work_public_id, access_class, publish_state, frozen = (
            work.public_id,
            str(work.access_class),
            str(work.publish_state),
            work.frozen,
        )
        label = page.label
    master = rt.ingest_store.get(settings.bucket_preservation, master_key)
    provider = rt.ocr_for(staging_prefix)
    result = await provider.recognize(master, page_ref=f"{seq:04d}.tif", language_hints=[language])
    alto_key = storage.alto_key(work_id, do_id, seq)
    offsets_key = storage.offsets_key(work_id, do_id, seq)
    rt.store.put(
        settings.bucket_access, alto_key, to_alto_xml(result.page), content_type="application/xml"
    )
    offsets = [o.as_dict() for o in offsets_map(result.page)]
    rt.store.put(
        settings.bucket_access,
        offsets_key,
        json.dumps(offsets).encode("utf-8"),
        content_type="application/json",
    )
    async with rt.database.session(RlsContext.system()) as session:
        await ingest_service.record_ocr(
            session,
            page_id,
            text=result.text,
            alto_key=alto_key,
            offsets_key=offsets_key,
            avg_confidence=result.average_confidence,
            min_confidence=result.min_confidence,
            engine=result.engine,
            engine_version=result.engine_version,
            flag_threshold=settings.ocr_flag_threshold,
        )
    rt.indexer.index_page(
        PageDocument(
            page_id=page_id,
            work_id=work_id,
            work_public_id=work_public_id,
            seq=seq,
            label=label,
            text=result.text,
            language=language,
            access_class=access_class,
            publish_state=publish_state,
            frozen=frozen,
        )
    )
    rt.send("jdhp.embeddings.compute", page_id=str(page_id))
    await maybe_finalize(rt, do_id)
    return {
        "page": str(page_id),
        "status": "recognized",
        "words": len(result.page.words),
        "average_confidence": round(result.average_confidence, 3),
    }
