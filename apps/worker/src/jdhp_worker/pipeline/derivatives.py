"""Access derivatives: a tiled pyramid for the image server, a thumbnail, a marked sample."""

from __future__ import annotations

import hashlib
import uuid

import pyvips

from jdhp_api.core import storage
from jdhp_api.core.db import RlsContext
from jdhp_api.core.orm import PremisEventType
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.catalog.service import in_sample_range
from jdhp_api.modules.ingest import service as ingest_service
from jdhp_api.modules.ingest.models import Page
from jdhp_worker.pipeline.finalize import maybe_finalize
from jdhp_worker.pipeline.watermark import platform_mark
from jdhp_worker.runtime import Runtime

AGENT = "jdhp-worker derivatives"


def access_derivative(master: bytes, fmt: str) -> bytes:
    image = pyvips.Image.new_from_buffer(master, "")
    if fmt == "jp2":
        return bytes(image.jp2ksave_buffer(Q=80, tile_width=1024, tile_height=1024))
    return bytes(
        image.tiffsave_buffer(
            tile=True, pyramid=True, compression="jpeg", Q=85, tile_width=256, tile_height=256
        )
    )


def webp_resized(master: bytes, width: int, *, mark: bool) -> bytes:
    """A WebP of the master scaled to ``width``, with the platform mark when ``mark`` is set."""
    image = pyvips.Image.new_from_buffer(master, "")
    if image.hasalpha():
        image = image.flatten()
    resized = image.resize(width / image.width, kernel="lanczos3")
    if mark:
        resized = platform_mark(resized)
    return bytes(resized.webpsave_buffer(Q=80, effort=4, strip=True))


async def generate_for_page(rt: Runtime, page_id: uuid.UUID) -> dict[str, object]:
    settings = rt.settings
    async with rt.database.session(RlsContext.system()) as session:
        page = await session.get(Page, page_id)
        if page is None or page.master_key is None:
            return {"page": str(page_id), "status": "missing"}
        work = await session.get(Work, page.work_id)
        if work is None:
            return {"page": str(page_id), "status": "missing"}
        seq, work_id, do_id, master_key = (
            page.seq,
            page.work_id,
            page.digital_object_id,
            page.master_key,
        )
        sample = in_sample_range(work, seq)
    master = rt.ingest_store.get(settings.bucket_preservation, master_key)
    fmt = settings.access_derivative_format
    derivative = access_derivative(master, fmt)
    derivative_key = storage.derivative_key(work_id, do_id, seq, fmt)
    thumb_key = storage.thumb_key(work_id, do_id, seq)
    content_type = "image/jp2" if fmt == "jp2" else "image/tiff"
    rt.store.put(settings.bucket_access, derivative_key, derivative, content_type=content_type)
    rt.store.put(
        settings.bucket_access,
        thumb_key,
        webp_resized(master, settings.thumbnail_width, mark=False),
        content_type="image/webp",
    )
    sample_key = None
    if sample:
        sample_key = storage.sample_key(work_id, do_id, seq)
        rt.store.put(
            settings.bucket_access,
            sample_key,
            webp_resized(master, settings.sample_width, mark=True),
            content_type="image/webp",
        )
    async with rt.database.session(RlsContext.system()) as session:
        await ingest_service.record_derivatives(
            session,
            page_id,
            derivative_key=derivative_key,
            derivative_sha256=hashlib.sha256(derivative).hexdigest(),
            thumb_key=thumb_key,
            sample_key=sample_key,
        )
        await ingest_service.write_premis(
            session,
            do_id,
            event_type=PremisEventType.DERIVATIVE_GENERATION,
            outcome="success",
            agent=AGENT,
            detail={"format": fmt, "sample": sample},
            page_id=page_id,
        )
    await maybe_finalize(rt, do_id)
    return {"page": str(page_id), "status": "derived", "format": fmt, "sample": sample}
