"""Embeddings per page chunk, with model and version recorded (SRCH-6)."""

from __future__ import annotations

import uuid

from jdhp_api.core.db import RlsContext
from jdhp_api.modules.content.service import replace_page_embeddings
from jdhp_api.modules.ingest.models import Page
from jdhp_worker.pipeline.failures import record_failure
from jdhp_worker.runtime import Runtime

AGENT = "jdhp-worker embeddings"


def chunk_text(text: str, size: int) -> list[str]:
    """Split on line boundaries into chunks of roughly ``size`` characters."""
    chunks: list[str] = []
    current: list[str] = []
    length = 0
    for line in text.splitlines():
        if current and length + len(line) + 1 > size:
            chunks.append("\n".join(current))
            current, length = [], 0
        current.append(line)
        length += len(line) + 1
    if current:
        chunks.append("\n".join(current))
    return [c for c in chunks if c.strip()]


async def compute_for_page(rt: Runtime, page_id: uuid.UUID) -> dict[str, object]:
    async with rt.database.session(RlsContext.system()) as session:
        page = await session.get(Page, page_id)
        if page is None or not page.ocr_text:
            return {"page": str(page_id), "status": "no-text"}
        text = page.ocr_text
        do_id = page.digital_object_id
    chunks = chunk_text(text, rt.settings.embedding_chunk_chars)
    if not chunks:
        return {"page": str(page_id), "status": "no-text"}
    try:
        result = await rt.embeddings.embed(chunks)
        async with rt.database.session(RlsContext.system()) as session:
            page = await session.get(Page, page_id)
            if page is None:
                return {"page": str(page_id), "status": "missing"}
            count = await replace_page_embeddings(
                session,
                page,
                chunks=chunks,
                vectors=result.vectors,
                model=result.model,
                model_version=result.model_version,
                dimensions=result.dimensions,
            )
    except Exception as exc:
        await record_failure(
            rt, digital_object_id=do_id, stage="embeddings", exc=exc, agent=AGENT, page_id=page_id
        )
        raise
    return {"page": str(page_id), "status": "embedded", "chunks": count, "model": result.model}
