"""Loader for review tasks, addressed by the public identifier of the content object they review."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core.auth import Principal
from jdhp_api.core.authz import ResourceRef
from jdhp_api.core.errors import InvalidIdentifierError, NotFoundError
from jdhp_api.core.ids import is_valid_name
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.content.models import ContentObject
from jdhp_api.modules.review import service
from jdhp_api.modules.review.models import ReviewTask


async def load_task(
    request: Request, session: AsyncSession, _principal: Principal
) -> tuple[tuple[ReviewTask, ContentObject, Work], ResourceRef]:
    public_id = str(request.path_params.get("public_id", ""))
    if not is_valid_name(public_id):
        raise InvalidIdentifierError
    found = await service.get_task_for_content(session, public_id)
    if found is None:
        raise NotFoundError
    task, obj = found
    work = await session.get(Work, task.work_id)
    if work is None:
        raise NotFoundError
    attr = {"state": str(task.state), "assignee_id": str(task.assignee_id or "")}
    return (task, obj, work), ResourceRef(kind="review_task", id=obj.public_id, attr=attr)
