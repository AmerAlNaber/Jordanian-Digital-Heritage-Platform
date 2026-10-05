"""Content service. AI objects are born pending with a review task (REV-1, SRC-2)."""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from typing import Any

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core import audit
from jdhp_api.core.auth import Principal
from jdhp_api.core.config import Settings
from jdhp_api.core.errors import NotFoundError
from jdhp_api.core.ids import format_ark, mint_name
from jdhp_api.core.orm import AuditOutcome, Origin, ProvenanceType, ReviewStatus
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.content.models import ContentObject
from jdhp_api.modules.content.schemas import ContentObjectCreate, ContentObjectOut
from jdhp_api.modules.ingest.models import Page
from jdhp_api.modules.review.models import ReviewTask

CONTENT_SHOULDER = "t8"

LABELS = {
    ProvenanceType.TRANSCRIPTION: ("نسخ", "Transcription"),
    ProvenanceType.TRANSLATION: ("ترجمة", "Translation"),
    ProvenanceType.EDITORIAL: ("ملاحظة تحريرية", "Editorial note"),
    ProvenanceType.VISUALIZATION: ("تصوّر", "Visualization"),
    ProvenanceType.SCAN: ("المسح الأصلي", "Original scan"),
    ProvenanceType.OCR: ("نص داخلي", "Internal text"),
}


def label_for(obj: ContentObject) -> tuple[str, str]:
    kind_ar, kind_en = LABELS[obj.provenance_type]
    if obj.origin == Origin.AI:
        who_ar, who_en = "أنتجه نموذج ذكاء اصطناعي", "produced by an AI model"
        if obj.review_status == ReviewStatus.APPROVED and obj.reviewer_subject:
            who_ar += f"، راجعه {obj.reviewer_name or 'مراجع'}"
            who_en += f", reviewed by {obj.reviewer_name or 'a reviewer'}"
    else:
        who_ar, who_en = "من إعداد إنسان", "prepared by a person"
    return f"{kind_ar}: {who_ar}", f"{kind_en}: {who_en}"


def visible_content(stmt: Select[Any], principal: Principal) -> Select[Any]:
    """Non-staff never see an unapproved AI object, in any list (REV-1)."""
    if principal.is_staff:
        return stmt.where(ContentObject.deleted_at.is_(None))
    return stmt.where(
        ContentObject.deleted_at.is_(None),
        (ContentObject.origin == Origin.HUMAN)
        | (ContentObject.review_status == ReviewStatus.APPROVED),
    )


def attributes(obj: ContentObject, work: Work) -> dict[str, Any]:
    return {
        "origin": str(obj.origin),
        "review_status": str(obj.review_status),
        "provenance_type": str(obj.provenance_type),
        "work_access_class": str(work.access_class),
        "work_publish_state": str(work.publish_state),
    }


async def get_by_public_id(session: AsyncSession, public_id: str) -> ContentObject | None:
    return (
        await session.scalars(
            select(ContentObject).where(
                ContentObject.public_id == public_id, ContentObject.deleted_at.is_(None)
            )
        )
    ).first()


async def list_for_work(
    session: AsyncSession,
    work: Work,
    principal: Principal,
    *,
    page_seq: int | None,
    provenance_type: ProvenanceType | None,
) -> list[ContentObject]:
    stmt = visible_content(select(ContentObject).where(ContentObject.work_id == work.id), principal)
    if page_seq is not None:
        stmt = stmt.join(Page, Page.id == ContentObject.page_id).where(Page.seq == page_seq)
    if provenance_type is not None:
        stmt = stmt.where(ContentObject.provenance_type == provenance_type)
    rows = await session.scalars(stmt.order_by(ContentObject.created_at.asc()))
    return list(rows.all())


async def to_out(
    session: AsyncSession, objects: Sequence[ContentObject], work: Work, settings: Settings
) -> list[ContentObjectOut]:
    page_ids = [o.page_id for o in objects if o.page_id is not None]
    seqs: dict[Any, int] = {}
    if page_ids:
        rows = await session.execute(select(Page.id, Page.seq).where(Page.id.in_(page_ids)))
        seqs = {page_id: int(seq) for page_id, seq in rows.all()}
    out: list[ContentObjectOut] = []
    for obj in objects:
        label_ar, label_en = label_for(obj)
        out.append(
            ContentObjectOut(
                public_id=obj.public_id,
                ark=format_ark(settings.ark_naan, obj.public_id),
                work_public_id=work.public_id,
                page_seq=seqs.get(obj.page_id) if obj.page_id else None,
                provenance_type=obj.provenance_type,
                origin=obj.origin,
                language=obj.language,
                script=obj.script,
                body=obj.body,
                segments=obj.segments,
                model=obj.model,
                model_version=obj.model_version,
                review_status=obj.review_status,
                reviewed_at=obj.reviewed_at,
                reviewer_subject=obj.reviewer_subject,
                generated_at=obj.generated_at,
                created_at=obj.created_at,
                label_ar=label_ar,
                label_en=label_en,
            )
        )
    return out


async def create(
    session: AsyncSession,
    work: Work,
    data: ContentObjectCreate,
    *,
    actor_id: str,
    actor_roles: frozenset[str] | tuple[str, ...],
    created_by: Any,
    request_id: str | None,
) -> ContentObject:
    """Create a content object. AI origin forces pending and opens a review task (REV-1)."""
    page_id = None
    if data.page_seq is not None:
        page = await session.scalar(
            select(Page).where(Page.work_id == work.id, Page.seq == data.page_seq)
        )
        if page is None:
            raise NotFoundError
        page_id = page.id
    is_ai = data.origin == Origin.AI
    obj = ContentObject(
        public_id=mint_name(CONTENT_SHOULDER),
        work_id=work.id,
        page_id=page_id,
        provenance_type=data.provenance_type,
        origin=data.origin,
        language=data.language,
        script=data.script,
        body=data.body,
        segments=data.segments,
        model=data.model,
        model_version=data.model_version,
        prompt_template_version=data.prompt_template_version,
        glossary_version=data.glossary_version,
        self_assessment=data.self_assessment,
        review_status=ReviewStatus.PENDING if is_ai else ReviewStatus.APPROVED,
        generated_at=dt.datetime.now(dt.UTC) if is_ai else None,
        created_by=created_by,
    )
    session.add(obj)
    await session.flush()
    if is_ai:
        session.add(
            ReviewTask(content_object_id=obj.id, work_id=work.id, state=ReviewStatus.PENDING)
        )
        await session.flush()
    await audit.write(
        session,
        actor_id=actor_id,
        actor_type="user" if actor_id != "system" else "system",
        actor_roles=actor_roles,
        action="content.create",
        resource_kind="content_object",
        resource_id=obj.public_id,
        outcome=AuditOutcome.SUCCESS,
        details={
            "origin": str(obj.origin),
            "provenance_type": str(obj.provenance_type),
            "work": work.public_id,
        },
        request_id=request_id,
    )
    return obj


async def replace_page_embeddings(
    session: AsyncSession,
    page: Page,
    *,
    chunks: Sequence[str],
    vectors: Sequence[Sequence[float]],
    model: str,
    model_version: str,
    dimensions: int,
) -> int:
    """Replace the page's vectors for one model and version (SRCH-6). Returns the row count."""
    import hashlib

    from sqlalchemy import delete

    from jdhp_api.modules.content.models import PageEmbedding

    await session.execute(
        delete(PageEmbedding).where(
            PageEmbedding.page_id == page.id,
            PageEmbedding.model == model,
            PageEmbedding.model_version == model_version,
        )
    )
    for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True)):
        session.add(
            PageEmbedding(
                page_id=page.id,
                chunk_index=index,
                embedding=list(vector),
                dimensions=dimensions,
                model=model,
                model_version=model_version,
                chunk_hash=hashlib.sha256(chunk.encode("utf-8")).hexdigest(),
            )
        )
    await session.flush()
    return len(chunks)
