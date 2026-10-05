"""Account routes: the signed-in user's own profile, preferences, phone and sessions.

ACC-1 (phone verification), ACC-5 (own profile), SEC-5 (sessions the user can see and end).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from jdhp_api.core.authz import Authorize, Authorized
from jdhp_api.core.config import Settings
from jdhp_api.core.deps import current_settings
from jdhp_api.core.messaging import SmsSender
from jdhp_api.modules.identity import service
from jdhp_api.modules.identity.schemas import (
    Me,
    PhoneConfirm,
    PhoneStart,
    PhoneStatus,
    PreferencesUpdate,
    SessionsOut,
)
from jdhp_api.modules.reader.service import ReaderServices, RequestFacts

router = APIRouter(tags=["identity"])


def get_sms_sender(request: Request) -> SmsSender:
    return request.app.state.sms_sender  # type: ignore[no-any-return]


def get_reader_services(request: Request) -> ReaderServices:
    return request.app.state.reader  # type: ignore[no-any-return]


def _facts(request: Request, authorized: Authorized) -> RequestFacts:
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip()[:45] if forwarded else None
    if ip is None and request.client:
        ip = request.client.host
    return RequestFacts(
        request_id=authorized.request_id, ip=ip, user_agent=request.headers.get("user-agent")
    )


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


@router.get("/me/phone", response_model=PhoneStatus)
async def get_phone(
    authorized: Annotated[Authorized, Depends(Authorize("view_self", "user"))],
) -> PhoneStatus:
    return await service.phone_status(authorized.session, authorized.principal)


@router.post("/me/phone", response_model=PhoneStatus, status_code=status.HTTP_202_ACCEPTED)
async def start_phone(
    data: PhoneStart,
    authorized: Annotated[Authorized, Depends(Authorize("edit_self", "user"))],
    settings: Annotated[Settings, Depends(current_settings)],
    sms: Annotated[SmsSender, Depends(get_sms_sender)],
) -> PhoneStatus:
    """Send a one-time code to the number (ACC-1). Three an hour, a minute apart."""
    return await service.start_phone_verification(
        authorized.session,
        authorized.principal,
        phone_number=data.phone_number,
        settings=settings,
        sms=sms,
        request_id=authorized.request_id,
    )


@router.post("/me/phone/verify", response_model=Me)
async def verify_phone(
    data: PhoneConfirm,
    authorized: Annotated[Authorized, Depends(Authorize("edit_self", "user"))],
    settings: Annotated[Settings, Depends(current_settings)],
) -> Me:
    """Confirm the code; a verified phone raises the member's verification level (ACC-1)."""
    return await service.confirm_phone_verification(
        authorized.session,
        authorized.principal,
        code=data.code,
        settings=settings,
        request_id=authorized.request_id,
    )


@router.get("/me/sessions", response_model=SessionsOut)
async def list_sessions(
    authorized: Annotated[Authorized, Depends(Authorize("list_sessions", "user"))],
) -> SessionsOut:
    """The user's open readers and the sign-in each belongs to (SEC-5)."""
    return await service.list_sessions(authorized.session, authorized.principal)


@router.delete("/me/sessions/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(
    name: str,
    request: Request,
    authorized: Annotated[Authorized, Depends(Authorize("revoke_session", "user"))],
    services: Annotated[ReaderServices, Depends(get_reader_services)],
) -> Response:
    """End one of the user's own readers; it goes dark within the cache window (SEC-5)."""
    reader = await service.own_reader(authorized.session, authorized.principal, name)
    await service.revoke_reader(
        services, reader=reader, principal=authorized.principal, facts=_facts(request, authorized)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/me/sign-ins/{sid}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_sign_in(
    sid: str,
    request: Request,
    authorized: Annotated[Authorized, Depends(Authorize("revoke_session", "user"))],
    services: Annotated[ReaderServices, Depends(get_reader_services)],
) -> Response:
    """End every reader opened under one sign-in; the web application ends the sign-in itself."""
    await service.revoke_sign_in(
        services, principal=authorized.principal, sid=sid, facts=_facts(request, authorized)
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
