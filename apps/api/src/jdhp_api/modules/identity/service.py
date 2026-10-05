"""Identity service: the platform's view of a signed-in user.

Users are created the first time a verified token for them arrives (just-in-time), and their
role mirrors the realm roles in the token. Verification level and institution come from the
platform's own records, because researcher verification and institutional licensing are
platform workflows, not identity-provider facts.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from jdhp_api.core.auth import Principal, Role, UserFacts, VerificationLevel, roles_from_claims
from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.errors import UnauthorizedError
from jdhp_api.core.ids import uuid7
from jdhp_api.core.orm import UserRole, UserVerification
from jdhp_api.modules.identity.models import Institution, User
from jdhp_api.modules.identity.schemas import InstitutionRef, Me

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
    # Platform-decided levels (researcher, institutional) are never downgraded by token claims.
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
