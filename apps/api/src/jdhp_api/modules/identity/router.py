"""Account routes: the signed-in user's own profile and preferences (ACC-5)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from jdhp_api.core.authz import Authorize, Authorized
from jdhp_api.modules.identity import service
from jdhp_api.modules.identity.schemas import Me, PreferencesUpdate

router = APIRouter(tags=["identity"])


@router.get("/me", response_model=Me)
async def get_me(authorized: Annotated[Authorized, Depends(Authorize("view_self", "user"))]) -> Me:
    return await service.profile(authorized.session, authorized.principal)


@router.patch("/me/preferences", response_model=Me)
async def update_preferences(
    data: PreferencesUpdate,
    authorized: Annotated[Authorized, Depends(Authorize("edit_self", "user"))],
) -> Me:
    changes = data.model_dump(exclude_unset=True, exclude_none=True)
    return await service.update_preferences(authorized.session, authorized.principal, changes)
