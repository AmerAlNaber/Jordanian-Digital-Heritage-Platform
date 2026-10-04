"""Intake routes (ADM-1). Curators submit a manifest; the pipeline does the rest."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core.auth import Principal
from jdhp_api.core.authz import Authorize, Authorized, ResourceRef
from jdhp_api.core.config import Settings
from jdhp_api.core.deps import current_settings
from jdhp_api.core.errors import InvalidIdentifierError, NotFoundError
from jdhp_api.core.ids import is_valid_name
from jdhp_api.core.orm import IntakeState
from jdhp_api.core.pagination import PageParams, Paginated, page_params
from jdhp_api.core.tasks import TaskDispatcher, get_dispatcher
from jdhp_api.modules.ingest import service
from jdhp_api.modules.ingest.models import IntakeBatch
from jdhp_api.modules.ingest.schemas import IntakeBatchOut, IntakeManifest

router = APIRouter(prefix="/intake", tags=["intake"])


async def load_batch(
    request: Request, session: AsyncSession, _principal: Principal
) -> tuple[IntakeBatch, ResourceRef]:
    code = str(request.path_params.get("code", ""))
    if not is_valid_name(code):
        raise InvalidIdentifierError
    batch = await service.get_batch_by_code(session, code)
    if batch is None:
        raise NotFoundError
    return batch, ResourceRef(kind="intake_batch", id=batch.code, attr={"state": str(batch.state)})


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
    stmt = select(IntakeBatch)
    if state is not None:
        stmt = stmt.where(IntakeBatch.state == state)
    total = await authorized.session.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = await authorized.session.scalars(
        stmt.order_by(IntakeBatch.created_at.desc()).limit(page.limit).offset(page.offset)
    )
    items = [await service.batch_out(authorized.session, b) for b in rows.all()]
    return Paginated(items=items, total=int(total), limit=page.limit, offset=page.offset)


@router.get("/batches/{code}", response_model=IntakeBatchOut)
async def get_batch(
    authorized: Annotated[Authorized, Depends(Authorize("view", "intake_batch", load_batch))],
) -> IntakeBatchOut:
    return await service.batch_out(authorized.session, authorized.resource)
