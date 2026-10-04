"""Review portal routes (ADM-8). Reviewer role with MFA; the only path to ``approved``."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from jdhp_api.core.authz import Authorize, Authorized
from jdhp_api.core.config import Settings
from jdhp_api.core.deps import current_settings
from jdhp_api.core.orm import ReviewStatus
from jdhp_api.core.pagination import PageParams, Paginated, page_params
from jdhp_api.modules.review import service
from jdhp_api.modules.review.loaders import load_task
from jdhp_api.modules.review.schemas import ApproveRequest, RejectRequest, ReviewTaskOut

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/tasks", response_model=Paginated[ReviewTaskOut])
async def list_tasks(
    authorized: Annotated[Authorized, Depends(Authorize("list", "review_task"))],
    settings: Annotated[Settings, Depends(current_settings)],
    page: Annotated[PageParams, Depends(page_params)],
    state: ReviewStatus | None = None,
    work: Annotated[str | None, Query(max_length=32)] = None,
) -> Paginated[ReviewTaskOut]:
    rows, total = await service.list_tasks(
        authorized.session, state=state, work_public_id=work, limit=page.limit, offset=page.offset
    )
    items = [await service.task_out(authorized.session, t, c, w, settings) for t, c, w in rows]
    return Paginated(items=items, total=total, limit=page.limit, offset=page.offset)


@router.get("/tasks/{public_id}", response_model=ReviewTaskOut)
async def get_task(
    authorized: Annotated[Authorized, Depends(Authorize("view", "review_task", load_task))],
    settings: Annotated[Settings, Depends(current_settings)],
) -> ReviewTaskOut:
    task, obj, work = authorized.resource
    return await service.task_out(authorized.session, task, obj, work, settings)


@router.post("/tasks/{public_id}/approve", response_model=ReviewTaskOut)
async def approve_task(
    data: ApproveRequest,
    authorized: Annotated[Authorized, Depends(Authorize("approve", "review_task", load_task))],
    settings: Annotated[Settings, Depends(current_settings)],
) -> ReviewTaskOut:
    task, obj, work = authorized.resource
    await service.approve(
        authorized.session,
        task,
        obj,
        authorized.principal,
        edited_body=data.edited_body,
        note=data.note,
        request_id=authorized.request_id,
    )
    return await service.task_out(authorized.session, task, obj, work, settings)


@router.post("/tasks/{public_id}/reject", response_model=ReviewTaskOut)
async def reject_task(
    data: RejectRequest,
    authorized: Annotated[Authorized, Depends(Authorize("reject", "review_task", load_task))],
    settings: Annotated[Settings, Depends(current_settings)],
) -> ReviewTaskOut:
    task, obj, work = authorized.resource
    await service.reject(
        authorized.session,
        task,
        obj,
        authorized.principal,
        reason=data.reason,
        request_id=authorized.request_id,
    )
    return await service.task_out(authorized.session, task, obj, work, settings)
