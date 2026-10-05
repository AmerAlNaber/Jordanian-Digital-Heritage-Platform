"""Identity service: the platform's view of a signed-in user.

Users are created the first time a verified token for them arrives (just-in-time), and their
role mirrors the realm roles in the token. Verification level and institution come from the
platform's own records, because researcher verification and institutional licensing are
platform workflows, not identity-provider facts.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import secrets
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core import audit
from jdhp_api.core.auth import Principal, Role, UserFacts, VerificationLevel, roles_from_claims
from jdhp_api.core.config import Settings
from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.errors import (
    NotFoundError,
    PhoneCodeError,
    PhoneSendLimitError,
    UnauthorizedError,
)
from jdhp_api.core.ids import uuid7
from jdhp_api.core.messaging import SmsSender, mask_phone
from jdhp_api.core.orm import (
    AuditOutcome,
    AuditSeverity,
    ReaderSessionState,
    UserRole,
    UserVerification,
)
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.identity.models import Institution, PhoneVerification, User
from jdhp_api.modules.identity.schemas import (
    InstitutionRef,
    Me,
    PhoneStatus,
    ReaderSessionSummary,
    SessionsOut,
)
from jdhp_api.modules.reader import service as reader_service
from jdhp_api.modules.reader.models import ReaderSession

ROLE_PRECEDENCE = (
    Role.PLATFORM_ADMIN,
    Role.RIGHTS_OFFICER,
    Role.REVIEWER,
    Role.CURATOR,
    Role.INSTITUTION_ADMIN,
    Role.INSTITUTIONAL_USER,
    Role.VERIFIED_RESEARCHER,
    Role.MEMBER,
)

# Phone verification (ACC-1, SEC-4): a six-digit code, ten minutes, five attempts, three
# sends an hour and a minute between sends. The code is stored only as a keyed hash.
CODE_TTL = dt.timedelta(minutes=10)
MAX_ATTEMPTS = 5
SENDS_PER_WINDOW = 3
SEND_WINDOW = dt.timedelta(hours=1)
RESEND_GAP = dt.timedelta(seconds=60)


def primary_role(roles: frozenset[str]) -> UserRole:
    for role in ROLE_PRECEDENCE:
        if str(role) in roles:
            return UserRole(str(role))
    return UserRole.MEMBER


def verification_from_claims(claims: Mapping[str, Any]) -> UserVerification:
    if bool(claims.get("email_verified")) and bool(claims.get("phone_number_verified")):
        return UserVerification.PHONE
    if bool(claims.get("email_verified")):
        return UserVerification.EMAIL
    return UserVerification.NONE


async def get_by_subject(session: AsyncSession, subject: str) -> User | None:
    return (await session.scalars(select(User).where(User.keycloak_sub == subject))).first()


async def upsert_from_claims(session: AsyncSession, claims: Mapping[str, Any]) -> User:
    """Create or refresh the user row for verified claims. Called with the system context."""
    subject = str(claims["sub"])
    roles = roles_from_claims(claims)
    now = dt.datetime.now(dt.UTC)
    user = await get_by_subject(session, subject)
    claim_level = verification_from_claims(claims)
    if user is None:
        user = User(
            id=uuid7(),
            keycloak_sub=subject,
            email=claims.get("email"),
            display_name=claims.get("name") or claims.get("preferred_username"),
            role=primary_role(roles),
            verification_level=claim_level,
            last_seen_at=now,
        )
        session.add(user)
        await session.flush()
        return user
    user.role = primary_role(roles)
    user.last_seen_at = now
    if user.pseudonymized_at is None:
        user.email = claims.get("email") or user.email
        user.display_name = (
            claims.get("name") or claims.get("preferred_username") or user.display_name
        )
    # Platform-decided levels (researcher, institutional) are never downgraded by token claims,
    # and a phone the platform verified counts even when the token says nothing about it.
    if user.phone_verified_at is not None and claim_level == UserVerification.EMAIL:
        claim_level = UserVerification.PHONE
    if user.verification_level in {
        UserVerification.NONE,
        UserVerification.EMAIL,
        UserVerification.PHONE,
    }:
        user.verification_level = claim_level
    await session.flush()
    return user


def facts_for(user: User) -> UserFacts:
    return UserFacts(
        user_id=user.id,
        verification_level=VerificationLevel(str(user.verification_level)),
        institution_id=user.institution_id,
    )


class DatabaseUserSync:
    """The ``UserSync`` implementation wired into the application."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def __call__(self, claims: Mapping[str, Any]) -> UserFacts:
        async with self._database.session(RlsContext.system()) as session:
            user = await upsert_from_claims(session, claims)
            return facts_for(user)


# --- Own profile (ACC-5) -----------------------------------------------------------------------


async def profile(session: AsyncSession, principal: Principal) -> Me:
    user = await get_by_subject(session, principal.id)
    if user is None:
        raise UnauthorizedError
    institution = None
    if user.institution_id is not None:
        inst = await session.get(Institution, user.institution_id)
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
        mfa=principal.mfa,
        phone_number=mask_phone(user.phone_number) if user.phone_number else None,
        phone_verified_at=user.phone_verified_at,
    )


async def update_preferences(
    session: AsyncSession, principal: Principal, changes: dict[str, Any]
) -> Me:
    user = await get_by_subject(session, principal.id)
    if user is None:
        raise UnauthorizedError
    user.preferences = {**user.preferences, **changes}
    await session.flush()
    return await profile(session, principal)


# --- Phone verification (ACC-1) --------------------------------------------------------------


async def _require_user(session: AsyncSession, principal: Principal) -> User:
    user = await get_by_subject(session, principal.id)
    if user is None:
        raise UnauthorizedError
    return user


def _code_hash(settings: Settings, user_id: Any, code: str) -> str:
    key = settings.token_signing_key.get_secret_value().encode()
    return hmac.new(key, f"phone:{user_id}:{code}".encode(), hashlib.sha256).hexdigest()


def sms_body(code: str, locale: str | None) -> str:
    arabic = f"{code} هو رمز التحقق لمنصة التراث الأردني الرقمي. صالح لعشر دقائق."
    english = f"{code} is your Jordanian Digital Heritage Platform code. Valid for ten minutes."
    return english if locale == "en" else f"{arabic}\n{english}"


async def _pending_for(session: AsyncSession, user: User) -> PhoneVerification | None:
    stmt = select(PhoneVerification).where(PhoneVerification.user_id == user.id).with_for_update()
    return (await session.scalars(stmt)).first()


async def _audit_phone(
    session: AsyncSession,
    principal: Principal,
    action: str,
    *,
    outcome: AuditOutcome,
    details: dict[str, Any],
    request_id: str | None,
    severity: AuditSeverity = AuditSeverity.INFO,
) -> None:
    await audit.write(
        session,
        actor_id=principal.id,
        actor_type="user",
        actor_roles=principal.roles,
        action=action,
        resource_kind="user",
        resource_id=principal.id,
        outcome=outcome,
        severity=severity,
        details=details,
        request_id=request_id,
    )


def _status(user: User, pending: PhoneVerification | None, now: dt.datetime) -> PhoneStatus:
    live = pending is not None and pending.expires_at > now
    return PhoneStatus(
        phone_number=mask_phone(
            pending.phone_number if live and pending else (user.phone_number or "")
        )
        or None,
        verified_at=user.phone_verified_at,
        pending=live,
        expires_at=pending.expires_at if live and pending else None,
    )


async def phone_status(
    session: AsyncSession, principal: Principal, *, now: dt.datetime | None = None
) -> PhoneStatus:
    now = now or dt.datetime.now(dt.UTC)
    user = await _require_user(session, principal)
    pending = (
        await session.scalars(select(PhoneVerification).where(PhoneVerification.user_id == user.id))
    ).first()
    return _status(user, pending, now)


async def start_phone_verification(
    session: AsyncSession,
    principal: Principal,
    *,
    phone_number: str,
    settings: Settings,
    sms: SmsSender,
    request_id: str | None,
    now: dt.datetime | None = None,
) -> PhoneStatus:
    """Send a code to the number. Sends are capped per window and spaced a minute apart."""
    now = now or dt.datetime.now(dt.UTC)
    user = await _require_user(session, principal)
    pending = await _pending_for(session, user)
    if pending is not None:
        if now - pending.window_started_at >= SEND_WINDOW:
            pending.window_started_at = now
            pending.sends_in_window = 0
        if pending.sends_in_window >= SENDS_PER_WINDOW or now - pending.last_sent_at < RESEND_GAP:
            await _audit_phone(
                session,
                principal,
                "account.phone_code_limited",
                outcome=AuditOutcome.DENY,
                details={"phone": mask_phone(phone_number)},
                request_id=request_id,
                severity=AuditSeverity.NOTICE,
            )
            await session.commit()  # the refusal must outlive the error response
            raise PhoneSendLimitError
        pending.sends_in_window += 1
    else:
        pending = PhoneVerification(
            id=uuid7(),
            user_id=user.id,
            window_started_at=now,
            sends_in_window=1,
            created_by=user.id,
        )
        session.add(pending)
    code = f"{secrets.randbelow(10**6):06d}"
    pending.phone_number = phone_number
    pending.code_hash = _code_hash(settings, user.id, code)
    pending.expires_at = now + CODE_TTL
    pending.attempts = 0
    pending.last_sent_at = now
    await session.flush()
    await sms.send(phone_number, sms_body(code, str(user.preferences.get("locale") or "ar")))
    await _audit_phone(
        session,
        principal,
        "account.phone_code_sent",
        outcome=AuditOutcome.SUCCESS,
        details={"phone": mask_phone(phone_number)},
        request_id=request_id,
    )
    return _status(user, pending, now)


async def confirm_phone_verification(
    session: AsyncSession,
    principal: Principal,
    *,
    code: str,
    settings: Settings,
    request_id: str | None,
    now: dt.datetime | None = None,
) -> Me:
    """A right code within its life and attempts verifies the number and raises the level."""
    now = now or dt.datetime.now(dt.UTC)
    user = await _require_user(session, principal)
    pending = await _pending_for(session, user)
    reason = None
    if pending is None:
        reason = "none"
    elif pending.expires_at <= now:
        reason = "expired"
    else:
        pending.attempts += 1
        if pending.attempts > MAX_ATTEMPTS:
            reason = "exhausted"
        elif not hmac.compare_digest(pending.code_hash, _code_hash(settings, user.id, code)):
            reason = "mismatch" if pending.attempts < MAX_ATTEMPTS else "exhausted"
    if reason is not None:
        if pending is not None and reason != "mismatch":
            await session.delete(pending)
        await session.flush()
        await _audit_phone(
            session,
            principal,
            "account.phone_code_rejected",
            outcome=AuditOutcome.DENY,
            details={"reason": reason},
            request_id=request_id,
            severity=AuditSeverity.NOTICE,
        )
        # The request transaction rolls back on an error response; the attempt count and the
        # audit event must survive it, or guesses would be unlimited (SEC-4).
        await session.commit()
        raise PhoneCodeError
    assert pending is not None  # noqa: S101  # for the type checker; handled above
    user.phone_number = pending.phone_number
    user.phone_verified_at = now
    if user.verification_level in {UserVerification.NONE, UserVerification.EMAIL}:
        user.verification_level = UserVerification.PHONE
    await session.delete(pending)
    await session.flush()
    await _audit_phone(
        session,
        principal,
        "account.phone_verified",
        outcome=AuditOutcome.SUCCESS,
        details={"phone": mask_phone(user.phone_number)},
        request_id=request_id,
    )
    return await profile(session, principal)


# --- Sessions (SEC-5) -----------------------------------------------------------------------


async def list_sessions(
    session: AsyncSession, principal: Principal, *, now: dt.datetime | None = None
) -> SessionsOut:
    now = now or dt.datetime.now(dt.UTC)
    stmt = (
        select(ReaderSession, Work)
        .join(Work, Work.id == ReaderSession.work_id)
        .where(
            ReaderSession.user_id == principal.user_id,
            ReaderSession.state == ReaderSessionState.ACTIVE,
            ReaderSession.hard_expires_at > now,
            ReaderSession.idle_expires_at > now,
        )
        .order_by(ReaderSession.last_seen_at.desc())
    )
    readers = [
        ReaderSessionSummary(
            public_id=reader.public_id,
            work=work.public_id,
            title_ar=work.title_ar,
            title_en=work.title_en,
            device=reader.device_hash[:8],
            sign_in=reader.sid,
            current_sign_in=reader.sid is not None and reader.sid == principal.session_id,
            started_at=reader.created_at,
            last_seen_at=reader.last_seen_at,
            idle_expires_at=reader.idle_expires_at,
        )
        for reader, work in (await session.execute(stmt)).all()
    ]
    return SessionsOut(sign_in=principal.session_id, readers=readers)


async def own_reader(session: AsyncSession, principal: Principal, public_id: str) -> ReaderSession:
    stmt = select(ReaderSession).where(
        ReaderSession.public_id == public_id, ReaderSession.user_id == principal.user_id
    )
    reader = (await session.scalars(stmt)).first()
    if reader is None:
        raise NotFoundError
    return reader


async def revoke_reader(
    services: reader_service.ReaderServices,
    *,
    reader: ReaderSession,
    principal: Principal,
    facts: reader_service.RequestFacts,
) -> None:
    await reader_service.revoke_reader(services, reader=reader, principal=principal, facts=facts)


async def revoke_sign_in(
    services: reader_service.ReaderServices,
    *,
    principal: Principal,
    sid: str,
    facts: reader_service.RequestFacts,
) -> int:
    if principal.user_id is None:
        raise UnauthorizedError
    return await reader_service.end_sessions_for_sign_in(
        services, user_id=principal.user_id, sid=sid, principal=principal, facts=facts
    )
