"""Intake service: registers a batch, its work, item, digital object and pages, then hands the
heavy lifting to the pipeline. The worker calls the ``record_*`` functions as it progresses."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core import audit
from jdhp_api.core.auth import Principal
from jdhp_api.core.config import Settings
from jdhp_api.core.errors import NotFoundError
from jdhp_api.core.ids import mint_name
from jdhp_api.core.orm import (
    AuditOutcome,
    DigitalObjectState,
    DigitizationStatus,
    FixityStatus,
    IntakeState,
    PremisEventType,
    ReadingDirection,
)
from jdhp_api.modules.catalog.models import Item, Work
from jdhp_api.modules.catalog.service import create_work, get_work_by_name
from jdhp_api.modules.ingest.models import DigitalObject, IntakeBatch, Page, PremisEvent
from jdhp_api.modules.ingest.schemas import IntakeBatchOut, IntakeManifest

BATCH_SHOULDER = "b8"
INGEST_TASK = "jdhp.ingest.package"


async def register_batch(
    session: AsyncSession,
    manifest: IntakeManifest,
    principal: Principal,
    settings: Settings,
    *,
    request_id: str | None,
) -> IntakeBatch:
    if manifest.new_work is not None:
        work = await create_work(
            session, manifest.new_work, principal, settings, request_id=request_id
        )
    else:
        assert manifest.work_public_id is not None  # noqa: S101 - guaranteed by the schema validator
        found = await get_work_by_name(session, manifest.work_public_id)
        if found is None:
            raise NotFoundError
        work = found

    item = Item(
        work_id=work.id,
        shelfmark=manifest.item.shelfmark,
        condition=manifest.item.condition,
        provenance=manifest.item.provenance,
        digitization_status=DigitizationStatus.IN_PROGRESS,
        created_by=principal.user_id,
    )
    session.add(item)
    await session.flush()

    digital_object = DigitalObject(
        work_id=work.id,
        item_id=item.id,
        page_count=len(manifest.pages),
        state=DigitalObjectState.DRAFT,
        created_by=principal.user_id,
    )
    session.add(digital_object)
    await session.flush()

    rtl_scripts = {"Arab", "Hebr", "Syrc"}
    for page in manifest.pages:
        script = page.script or work.script
        session.add(
            Page(
                digital_object_id=digital_object.id,
                work_id=work.id,
                seq=page.seq,
                label=page.label,
                page_type=page.page_type,
                language=page.language or work.language,
                script=script,
                reading_direction=ReadingDirection.RTL
                if script in rtl_scripts
                else ReadingDirection.LTR,
                capture_date=manifest.capture.captured_on,
                capture_device=manifest.capture.device,
                color_target_ref=manifest.capture.color_target_ref,
                section_title=page.section_title,
                description=page.description,
                master_sha256=page.sha256,
                created_by=principal.user_id,
            )
        )

    batch = IntakeBatch(
        code=mint_name(BATCH_SHOULDER),
        work_id=work.id,
        item_id=item.id,
        digital_object_id=digital_object.id,
        manifest=manifest.model_dump(mode="json"),
        staging_prefix=manifest.staging_prefix,
        page_count=len(manifest.pages),
        state=IntakeState.RECEIVED,
        submitted_by=principal.user_id,
        created_by=principal.user_id,
    )
    session.add(batch)
    await session.flush()
    await audit.write(
        session,
        actor_id=principal.id,
        actor_type="user",
        actor_roles=principal.roles,
        action="intake.submit",
        resource_kind="intake_batch",
        resource_id=batch.code,
        outcome=AuditOutcome.SUCCESS,
        details={"work": work.public_id, "pages": len(manifest.pages)},
        request_id=request_id,
    )
    return batch


async def get_batch_by_code(session: AsyncSession, code: str) -> IntakeBatch | None:
    return (await session.scalars(select(IntakeBatch).where(IntakeBatch.code == code))).first()


async def batch_out(session: AsyncSession, batch: IntakeBatch) -> IntakeBatchOut:
    work = await session.get(Work, batch.work_id) if batch.work_id else None
    return IntakeBatchOut(
        code=batch.code,
        state=batch.state,
        work_public_id=work.public_id if work else "",
        page_count=batch.page_count,
        error_detail=batch.error_detail,
        created_at=batch.created_at,
        completed_at=batch.completed_at,
    )


# --- Pipeline callbacks (called by the worker through the same code path, ADR-0001 D17) ----


async def mark_batch_state(
    session: AsyncSession, batch_id: uuid.UUID, state: IntakeState, *, error: str | None = None
) -> IntakeBatch:
    batch = await session.get(IntakeBatch, batch_id)
    if batch is None:
        raise NotFoundError
    batch.state = state
    batch.error_detail = error
    if state in {IntakeState.INGESTED, IntakeState.FAILED}:
        batch.completed_at = dt.datetime.now(dt.UTC)
    await session.flush()
    return batch


async def record_master(
    session: AsyncSession,
    page_id: uuid.UUID,
    *,
    master_key: str,
    sha256: str,
    width_px: int,
    height_px: int,
) -> Page:
    page = await session.get(Page, page_id)
    if page is None:
        raise NotFoundError
    page.master_key = master_key
    page.master_sha256 = sha256
    page.width_px = width_px
    page.height_px = height_px
    page.last_fixity_at = dt.datetime.now(dt.UTC)
    await session.flush()
    return page


async def record_derivatives(
    session: AsyncSession,
    page_id: uuid.UUID,
    *,
    derivative_key: str,
    derivative_sha256: str,
    thumb_key: str,
    sample_key: str | None,
) -> Page:
    page = await session.get(Page, page_id)
    if page is None:
        raise NotFoundError
    page.derivative_key = derivative_key
    page.derivative_sha256 = derivative_sha256
    page.thumb_key = thumb_key
    page.sample_key = sample_key
    await session.flush()
    return page


async def record_ocr(
    session: AsyncSession,
    page_id: uuid.UUID,
    *,
    text: str,
    alto_key: str,
    offsets_key: str,
    avg_confidence: float,
    min_confidence: float,
    engine: str,
    engine_version: str,
    flag_threshold: float = 0.85,
) -> Page:
    page = await session.get(Page, page_id)
    if page is None:
        raise NotFoundError
    page.ocr_text = text
    page.alto_key = alto_key
    page.offsets_key = offsets_key
    page.ocr_avg_confidence = avg_confidence
    page.ocr_min_confidence = min_confidence
    page.ocr_engine = engine
    page.ocr_engine_version = engine_version
    page.ocr_at = dt.datetime.now(dt.UTC)
    page.ocr_flagged = avg_confidence < flag_threshold
    await session.flush()
    return page


async def write_premis(
    session: AsyncSession,
    digital_object_id: uuid.UUID,
    *,
    event_type: PremisEventType,
    outcome: str,
    agent: str,
    detail: dict[str, Any] | None = None,
    page_id: uuid.UUID | None = None,
) -> PremisEvent:
    event = PremisEvent(
        digital_object_id=digital_object_id,
        page_id=page_id,
        event_type=event_type,
        outcome=outcome,
        detail=detail or {},
        agent=agent,
        occurred_at=dt.datetime.now(dt.UTC),
    )
    session.add(event)
    await session.flush()
    return event


async def set_digital_object_state(
    session: AsyncSession,
    digital_object_id: uuid.UUID,
    state: DigitalObjectState,
    *,
    mets_key: str | None = None,
    fixity: FixityStatus | None = None,
    frozen_reason: str | None = None,
) -> DigitalObject:
    digital_object = await session.get(DigitalObject, digital_object_id)
    if digital_object is None:
        raise NotFoundError
    digital_object.state = state
    if mets_key is not None:
        digital_object.mets_key = mets_key
    if fixity is not None:
        digital_object.fixity_status = fixity
        digital_object.last_fixity_at = dt.datetime.now(dt.UTC)
    if state == DigitalObjectState.READY:
        digital_object.ingested_at = dt.datetime.now(dt.UTC)
        item = await session.get(Item, digital_object.item_id) if digital_object.item_id else None
        if item is not None:
            item.digitization_status = DigitizationStatus.DONE
    if state == DigitalObjectState.FROZEN:
        digital_object.frozen_reason = frozen_reason
        work = await session.get(Work, digital_object.work_id)
        if work is not None:
            work.frozen = True
    await session.flush()
    return digital_object
