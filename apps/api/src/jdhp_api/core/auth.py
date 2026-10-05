"""Authentication: verify access tokens from Keycloak and build the principal (SEC-1, SEC-2).

The API never sees a password. It accepts only signed access tokens issued by the identity
provider, verifies them against the provider's JWKS, refuses tokens that outlive the
ten-minute policy, and derives the principal that every policy decision uses. A request
without a token is the ``anonymous`` principal, which is still authorized by the engine.
"""

from __future__ import annotations

import enum
import json
import time
import uuid
from collections.abc import Mapping
from typing import Any, Protocol

import jwt
from fastapi import Depends, Request
from jwt import PyJWK, PyJWKClient, PyJWKSet
from pydantic import BaseModel, ConfigDict

from jdhp_api.core.config import Settings, get_settings
from jdhp_api.core.db import ANONYMOUS_ROLE, RlsContext
from jdhp_api.core.errors import UnauthorizedError

ALLOWED_ALGORITHMS = ("RS256", "PS256", "ES256")
LEEWAY_SECONDS = 10


class Role(enum.StrEnum):
    """Realm roles. Anyone signed in without a staff or institutional role is a member."""

    MEMBER = "member"
    VERIFIED_RESEARCHER = "verified_researcher"
    INSTITUTIONAL_USER = "institutional_user"
    INSTITUTION_ADMIN = "institution_admin"
    CURATOR = "curator"
    REVIEWER = "reviewer"
    RIGHTS_OFFICER = "rights_officer"
    PLATFORM_ADMIN = "platform_admin"


STAFF_ROLES = frozenset({Role.CURATOR, Role.REVIEWER, Role.RIGHTS_OFFICER, Role.PLATFORM_ADMIN})
KNOWN_ROLES = frozenset(str(role) for role in Role)


class VerificationLevel(enum.StrEnum):
    NONE = "none"
    EMAIL = "email"
    PHONE = "phone"
    RESEARCHER = "researcher"
    INSTITUTIONAL = "institutional"


class UserFacts(BaseModel):
    """What the platform knows about a signed-in user beyond the token."""

    model_config = ConfigDict(frozen=True)

    user_id: uuid.UUID | None = None
    verification_level: VerificationLevel = VerificationLevel.NONE
    institution_id: uuid.UUID | None = None
    active_devices: int = 0


class Principal(BaseModel):
    """The subject of every authorization decision."""

    model_config = ConfigDict(frozen=True)

    id: str
    roles: frozenset[str]
    authenticated: bool
    verification_level: VerificationLevel = VerificationLevel.NONE
    institution_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    mfa: bool = False
    session_age_seconds: int = 0
    active_devices: int = 0
    session_id: str | None = None  # the identity provider's sign-in session (SEC-5)
    token_id: str | None = None

    @classmethod
    def anonymous(cls) -> Principal:
        return cls(id=ANONYMOUS_ROLE, roles=frozenset({ANONYMOUS_ROLE}), authenticated=False)

    @property
    def is_staff(self) -> bool:
        return bool(self.roles & {str(role) for role in STAFF_ROLES})

    def rls_context(self) -> RlsContext:
        if not self.authenticated:
            return RlsContext.anonymous()
        return RlsContext(
            user_id=str(self.user_id or self.id),
            roles=tuple(sorted(self.roles)),
            institution_id=str(self.institution_id or ""),
        )

    def cerbos_attributes(self) -> dict[str, Any]:
        return {
            "authenticated": self.authenticated,
            "verification_level": str(self.verification_level),
            "institution_id": str(self.institution_id) if self.institution_id else "",
            "mfa": self.mfa,
            "session_age_seconds": self.session_age_seconds,
            "active_devices": self.active_devices,
            "is_staff": self.is_staff,
        }


class UserSync(Protocol):
    """Looks up or creates the platform user for verified token claims."""

    async def __call__(self, claims: Mapping[str, Any]) -> UserFacts: ...


async def claims_only_user_sync(claims: Mapping[str, Any]) -> UserFacts:
    """Fallback used before the identity module is wired: facts from the token alone."""
    email_verified = bool(claims.get("email_verified"))
    phone_verified = bool(claims.get("phone_number_verified"))
    level = VerificationLevel.NONE
    if email_verified and phone_verified:
        level = VerificationLevel.PHONE
    elif email_verified:
        level = VerificationLevel.EMAIL
    return UserFacts(verification_level=level)


class TokenVerifier:
    """Verifies signature, issuer, audience, lifetime and age of an access token."""

    def __init__(self, settings: Settings) -> None:
        self._issuer = str(settings.oidc_issuer).rstrip("/")
        self._audience = settings.oidc_audience
        self._max_age = settings.access_token_max_age_seconds
        self._static_keys: PyJWKSet | None = None
        self._client: PyJWKClient | None = None
        if settings.oidc_jwks_json is not None:
            self._static_keys = PyJWKSet.from_dict(
                json.loads(settings.oidc_jwks_json.get_secret_value())
            )
        else:
            self._client = PyJWKClient(settings.jwks_url, cache_keys=True, lifespan=300)

    def _key_for(self, token: str) -> PyJWK:
        if self._static_keys is not None:
            header = jwt.get_unverified_header(token)
            kid = header.get("kid")
            for key in self._static_keys.keys:
                if key.key_id == kid:
                    return key
            raise UnauthorizedError
        if self._client is None:  # pragma: no cover - one of the two is always set
            raise UnauthorizedError
        return self._client.get_signing_key_from_jwt(token)

    def verify(self, token: str) -> dict[str, Any]:
        try:
            key = self._key_for(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                key.key,
                algorithms=list(ALLOWED_ALGORITHMS),
                audience=self._audience,
                issuer=self._issuer,
                leeway=LEEWAY_SECONDS,
                options={"require": ["exp", "iat", "sub", "iss"]},
            )
        except jwt.PyJWTError as exc:
            raise UnauthorizedError from exc
        issued_at = int(claims["iat"])
        expires_at = int(claims["exp"])
        if expires_at - issued_at > self._max_age + LEEWAY_SECONDS:
            # Either the provider is misconfigured or the token was forged with a long life (SEC-2).
            raise UnauthorizedError
        if time.time() - issued_at > self._max_age + LEEWAY_SECONDS:
            raise UnauthorizedError
        return claims


def roles_from_claims(claims: Mapping[str, Any]) -> frozenset[str]:
    realm_access = claims.get("realm_access") or {}
    raw = realm_access.get("roles") if isinstance(realm_access, Mapping) else None
    roles = {str(r) for r in raw or () if str(r) in KNOWN_ROLES}
    if not roles:
        roles = {str(Role.MEMBER)}
    return frozenset(roles)


def mfa_from_claims(claims: Mapping[str, Any]) -> bool:
    amr = claims.get("amr") or []
    acr = str(claims.get("acr", ""))
    strong_methods = {"mfa", "otp", "hwk", "swk", "fido", "webauthn"}
    return bool(set(map(str, amr)) & strong_methods) or acr in {
        "2",
        "3",
        "aal2",
        "aal3",
        "gold",
        "platinum",
    }


def build_principal(claims: Mapping[str, Any], facts: UserFacts) -> Principal:
    auth_time = int(claims.get("auth_time") or claims["iat"])
    return Principal(
        id=str(claims["sub"]),
        roles=roles_from_claims(claims),
        authenticated=True,
        verification_level=facts.verification_level,
        institution_id=facts.institution_id,
        user_id=facts.user_id,
        mfa=mfa_from_claims(claims),
        session_age_seconds=max(0, int(time.time()) - auth_time),
        active_devices=facts.active_devices,
        token_id=str(claims["jti"]) if claims.get("jti") else None,
        session_id=str(claims["sid"]) if claims.get("sid") else None,
    )


def get_token_verifier(request: Request) -> TokenVerifier:
    verifier = getattr(request.app.state, "token_verifier", None)
    if verifier is None:
        verifier = TokenVerifier(get_settings())
        request.app.state.token_verifier = verifier
    return verifier


def get_user_sync(request: Request) -> UserSync:
    sync = getattr(request.app.state, "user_sync", None)
    return sync if sync is not None else claims_only_user_sync


def bearer_token(request: Request) -> str | None:
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise UnauthorizedError
    return token.strip()


async def get_principal(
    request: Request,
    verifier: TokenVerifier = Depends(get_token_verifier),
    user_sync: UserSync = Depends(get_user_sync),
) -> Principal:
    """The request's principal. Cached on the request so authorization and RLS agree."""
    cached = getattr(request.state, "principal", None)
    if cached is not None:
        return cached  # type: ignore[no-any-return]
    token = bearer_token(request)
    if token is None:
        principal = Principal.anonymous()
    else:
        claims = verifier.verify(token)
        facts = await user_sync(claims)
        principal = build_principal(claims, facts)
    request.state.principal = principal
    return principal
