"""SEC-1, SEC-2: tokens are verified against the provider's keys; lifetimes are enforced."""

from __future__ import annotations

import time
from collections.abc import Callable

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from jdhp_api.core.auth import (
    Principal,
    TokenVerifier,
    UserFacts,
    build_principal,
    mfa_from_claims,
    roles_from_claims,
)
from jdhp_api.core.config import Settings
from jdhp_api.core.errors import UnauthorizedError


def test_anonymous_principal_is_unauthenticated_with_the_anonymous_role() -> None:
    principal = Principal.anonymous()
    assert not principal.authenticated
    assert principal.roles == frozenset({"anonymous"})
    assert not principal.is_staff
    assert principal.rls_context().roles == ("anonymous",)


def test_sec_1_valid_token_verifies(settings: Settings, make_token: Callable[..., str]) -> None:
    verifier = TokenVerifier(settings)
    claims = verifier.verify(make_token("alice", ["member"]))
    assert claims["sub"] == "alice"


def test_sec_1_token_signed_by_another_key_is_refused(settings: Settings) -> None:
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = other.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    now = int(time.time())
    token = jwt.encode(
        {
            "iss": str(settings.oidc_issuer).rstrip("/"),
            "aud": settings.oidc_audience,
            "sub": "x",
            "iat": now,
            "exp": now + 60,
        },
        pem,
        algorithm="RS256",
        headers={"kid": "test-key-1"},
    )
    with pytest.raises(UnauthorizedError):
        TokenVerifier(settings).verify(token)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"audience": "someone-else"},
        {"issuer": "http://evil.test/realms/jdhp"},
        {"kid": "unknown-key"},
        {"issued_at": int(time.time()) - 3600},
    ],
)
def test_sec_1_wrong_audience_issuer_key_or_expired_is_refused(
    settings: Settings, make_token: Callable[..., str], kwargs: dict[str, object]
) -> None:
    with pytest.raises(UnauthorizedError):
        TokenVerifier(settings).verify(make_token("alice", **kwargs))  # type: ignore[arg-type]


def test_sec_2_token_living_longer_than_ten_minutes_is_refused(
    settings: Settings, make_token: Callable[..., str]
) -> None:
    with pytest.raises(UnauthorizedError):
        TokenVerifier(settings).verify(make_token("alice", lifetime=3600))


def test_sec_2_old_token_within_lifetime_but_past_max_age_is_refused(
    settings: Settings, make_token: Callable[..., str]
) -> None:
    # Issued 15 minutes ago with a forged 20-minute lifetime: valid by exp, refused by age.
    issued = int(time.time()) - 900
    with pytest.raises(UnauthorizedError):
        TokenVerifier(settings).verify(make_token("alice", issued_at=issued, lifetime=1200))


def test_roles_come_from_realm_access_and_default_to_member() -> None:
    assert roles_from_claims({"realm_access": {"roles": ["curator", "offline_access", "uma"]}}) == {
        "curator"
    }
    assert roles_from_claims({"realm_access": {"roles": ["offline_access"]}}) == {"member"}
    assert roles_from_claims({}) == {"member"}


def test_mfa_is_detected_from_amr_or_acr() -> None:
    assert mfa_from_claims({"amr": ["pwd", "otp"]})
    assert mfa_from_claims({"acr": "2"})
    assert not mfa_from_claims({"amr": ["pwd"], "acr": "1"})
    assert not mfa_from_claims({})


def test_build_principal_combines_claims_and_platform_facts() -> None:
    now = int(time.time())
    claims = {
        "sub": "bob",
        "iat": now - 120,
        "auth_time": now - 120,
        "jti": "abc",
        "realm_access": {"roles": ["reviewer"]},
        "amr": ["otp"],
    }
    principal = build_principal(claims, UserFacts(active_devices=2))
    assert principal.is_staff
    assert principal.mfa
    assert principal.active_devices == 2
    assert 115 <= principal.session_age_seconds <= 130
    attrs = principal.cerbos_attributes()
    assert attrs["is_staff"] is True
    assert attrs["authenticated"] is True
