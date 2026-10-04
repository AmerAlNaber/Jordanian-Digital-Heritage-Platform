"""Intake routes (ADM-1). Curators submit a manifest; the pipeline does the rest."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from jdhp_api.core.authz import Authorize, Authorized
from jdhp_api.core.config import Settings
from jdhp_api.core.deps import current_settings
from jdhp_api.core.orm import IntakeState
from jdhp_api.core.pagination import PageParams, Paginated, page_params
from jdhp_api.core.tasks import TaskDispatcher, get_dispatcher
from jdhp_api.modules.ingest import service
from jdhp_api.modules.ingest.loaders import load_batch
from jdhp_api.modules.ingest.schemas import IntakeBatchOut, IntakeManifest

router = APIRouter(prefix="/intake", tags=["intake"])


@router.post("/batches", response_model=IntakeBatchOut, status_code=status.HTTP_202_ACCEPTED)
async def submit_batch(
    manifest: IntakeManifest,
    authorized: Annotated[Authorized, Depends(Authorize("create", "intake_batch"))],
    settings: Annotated[Settings, Depends(current_settings)],
    dispatcher: Annotated[TaskDispatcher, Depends(get_dispatcher)],
) -> IntakeBatchOut:
    batch = await service.register_batch(
        authorized.session,
        manifest,
        authorized.principal,
        settings,
        request_id=authorized.request_id,
    )
    dispatcher.send(service.INGEST_TASK, batch_id=str(batch.id))
    return await service.batch_out(authorized.session, batch)


@router.get("/batches", response_model=Paginated[IntakeBatchOut])
async def list_batches(
    authorized: Annotated[Authorized, Depends(Authorize("list", "intake_batch"))],
    page: Annotated[PageParams, Depends(page_params)],
    state: IntakeState | None = None,
) -> Paginated[IntakeBatchOut]:
    items, total = await service.list_batches(
        authorized.session, state=state, limit=page.limit, offset=page.offset
    )
    return Paginated(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/batches/{code}", response_model=IntakeBatchOut)
async def get_batch(
    authorized: Annotated[Authorized, Depends(Authorize("view", "intake_batch", load_batch))],
) -> IntakeBatchOut:
    return await service.batch_out(authorized.session, authorized.resource)
