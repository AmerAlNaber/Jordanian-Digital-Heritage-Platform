"""Recording a pipeline failure where operators look for it (ADM-1).

A task that raises after the validation phase used to leave the intake batch in ``validating``
with no reason anywhere. Every pipeline stage now records the failure on the batch and as a
PREMIS event before the exception propagates to Celery, so the operator sees which page and
which stage failed and why.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select

from jdhp_api.core.db import RlsContext
from jdhp_api.core.orm import IntakeState, PremisEventType
from jdhp_api.modules.ingest import service as ingest_service
from jdhp_api.modules.ingest.models import IntakeBatch, Page
from jdhp_worker.runtime import Runtime

REASON_LIMIT = 200


def describe(exc: BaseException) -> str:
    message = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
    text = f"{exc.__class__.__name__}: {message}" if message else exc.__class__.__name__
    return text[:REASON_LIMIT]


async def record_failure(
    rt: Runtime,
    *,
    digital_object_id: uuid.UUID,
    stage: str,
    exc: BaseException,
    agent: str,
    event_type: PremisEventType = PremisEventType.INGEST,
    page_id: uuid.UUID | None = None,
) -> str:
    """Mark the batch ``failed`` with a readable reason and write a PREMIS fail event.

    Returns the reason recorded on the batch. Never raises on its own account: the caller
    re-raises the original exception, and a secondary failure here must not hide it.
    """
    reason = describe(exc)
    try:
        async with rt.database.session(RlsContext.system()) as session:
            page = await session.get(Page, page_id) if page_id is not None else None
            detail = (
                f"page {page.seq} {stage}: {reason}" if page is not None else f"{stage}: {reason}"
            )
            batch = (
                await session.scalars(
                    select(IntakeBatch).where(IntakeBatch.digital_object_id == digital_object_id)
                )
            ).first()
            if batch is not None:
                await ingest_service.mark_batch_state(
                    session, batch.id, IntakeState.FAILED, error=detail
                )
            await ingest_service.write_premis(
                session,
                digital_object_id,
                event_type=event_type,
                outcome="fail",
                agent=agent,
                detail={"stage": stage, "reason": reason},
                page_id=page_id,
            )
    except Exception:  # the original exception is what the operator must see
        return reason
    return detail
