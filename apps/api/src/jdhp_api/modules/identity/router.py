"""Account routes: the signed-in user's own profile and preferences (ACC-5)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select

from jdhp_api.core.authz import Authorize, Authorized
from jdhp_api.core.errors import UnauthorizedError
from jdhp_api.modules.identity.models import Institution, User
from jdhp_api.modules.identity.schemas import InstitutionRef, Me, PreferencesUpdate

router = APIRouter(tags=["identity"])


async def _me(authorized: Authorized) -> Me:
    user = await authorized.session.scalar(
        select(User).where(User.keycloak_sub == authorized.principal.id)
    )
    if user is None:
        raise UnauthorizedError
    institution = None
    if user.institution_id is not None:
        inst = await authorized.session.get(Institution, user.institution_id)
        if inst is not None:
            institution = InstitutionRef(slug=inst.slug, name_ar=inst.name_ar, name_en=inst.name_en)
    return Me(
        subject=user.keycloak_sub,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        verification_level=user.verification_level,
        institution=institution,
        preferences=user.preferences,
        mfa=authorized.principal.mfa,
    )


@router.get("/me", response_model=Me)
async def get_me(authorized: Annotated[Authorized, Depends(Authorize("view_self", "user"))]) -> Me:
    return await _me(authorized)


@router.patch("/me/preferences", response_model=Me)
async def update_preferences(
    data: PreferencesUpdate,
    authorized: Annotated[Authorized, Depends(Authorize("edit_self", "user"))],
) -> Me:
    user = await authorized.session.scalar(
        select(User).where(User.keycloak_sub == authorized.principal.id)
    )
    if user is None:
        raise UnauthorizedError
    user.preferences = {
        **user.preferences,
        **data.model_dump(exclude_unset=True, exclude_none=True),
    }
    await authorized.session.flush()
    return await _me(authorized)
