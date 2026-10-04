"""Loader for intake batches by their public code."""

from __future__ import annotations

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core.auth import Principal
from jdhp_api.core.authz import ResourceRef
from jdhp_api.core.errors import InvalidIdentifierError, NotFoundError
from jdhp_api.core.ids import is_valid_name
from jdhp_api.modules.ingest import service
from jdhp_api.modules.ingest.models import IntakeBatch


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
