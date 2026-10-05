"""Mark a digital object ready once every page has its derivative and its text. Idempotent."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select

from jdhp_api.core.db import RlsContext
from jdhp_api.core.orm import DigitalObjectState, IntakeState
from jdhp_api.modules.catalog.models import (
    Agent,
    Collection,
    CollectionWork,
    VocabularyTerm,
    Work,
    WorkAgent,
    WorkTerm,
)
from jdhp_api.modules.ingest import service as ingest_service
from jdhp_api.modules.ingest.models import DigitalObject, IntakeBatch, Page
from jdhp_api.modules.search.indexer import WorkDocument
from jdhp_worker.runtime import Runtime


async def maybe_finalize(rt: Runtime, digital_object_id: uuid.UUID) -> bool:
    async with rt.database.session(RlsContext.system()) as session:
        digital_object = await session.get(DigitalObject, digital_object_id)
        if digital_object is None or digital_object.state != DigitalObjectState.PROCESSING:
            return False
        total = await session.scalar(
            select(func.count())
            .select_from(Page)
            .where(Page.digital_object_id == digital_object_id)
        )
        done = await session.scalar(
            select(func.count())
            .select_from(Page)
            .where(
                Page.digital_object_id == digital_object_id,
                Page.derivative_key.is_not(None),
                Page.ocr_at.is_not(None),
            )
        )
        if not total or done != total:
            return False
        await ingest_service.set_digital_object_state(
            session, digital_object_id, DigitalObjectState.READY
        )
        batch = (
            await session.scalars(
                select(IntakeBatch).where(IntakeBatch.digital_object_id == digital_object_id)
            )
        ).first()
        if batch is not None:
            await ingest_service.mark_batch_state(session, batch.id, IntakeState.INGESTED)
        work = await session.get(Work, digital_object.work_id)
        document = await work_document(session, work) if work is not None else None
    # Indexing happens after the transaction commits: a search-index failure must not roll
    # the object back out of ``ingested`` (CAT-4).
    if document is not None:
        rt.indexer.index_work(document)
    return True


async def work_document(session: object, work: Work) -> WorkDocument:
    from sqlalchemy.ext.asyncio import AsyncSession

    assert isinstance(session, AsyncSession)  # noqa: S101 - narrow for typing
    agents = (
        await session.scalars(
            select(Agent.name_ar)
            .join(WorkAgent, WorkAgent.agent_id == Agent.id)
            .where(WorkAgent.work_id == work.id)
        )
    ).all()
    terms = (
        await session.execute(
            select(VocabularyTerm.pref_label_ar, WorkTerm.facet)
            .join(WorkTerm, WorkTerm.term_id == VocabularyTerm.id)
            .where(WorkTerm.work_id == work.id)
        )
    ).all()
    by_facet: dict[str, list[str]] = {}
    for label, facet in terms:
        by_facet.setdefault(str(facet), []).append(label)
    collections = (
        await session.scalars(
            select(Collection.public_id)
            .join(CollectionWork, CollectionWork.collection_id == Collection.id)
            .where(CollectionWork.work_id == work.id)
        )
    ).all()
    return WorkDocument(
        work_id=work.id,
        public_id=work.public_id,
        title_ar=work.title_ar,
        title_translit=work.title_translit,
        title_en=work.title_en,
        description_ar=work.description_ar,
        description_en=work.description_en,
        agents=list(agents),
        subjects=by_facet.get("subject", []),
        places=by_facet.get("place", []),
        periods=by_facet.get("period", []),
        collections=list(collections),
        language=work.language,
        date_earliest=work.date_earliest.isoformat() if work.date_earliest else None,
        date_latest=work.date_latest.isoformat() if work.date_latest else None,
        access_class=str(work.access_class),
        publish_state=str(work.publish_state),
        frozen=work.frozen,
    )
