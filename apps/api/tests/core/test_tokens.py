"""Reader credentials (SEC-2, SEC-10, SEC-11): bound, short-lived, tamper-evident, sealed."""

from __future__ import annotations

import base64
import datetime as dt
import uuid

import pytest
from pydantic import SecretStr

from jdhp_api.core.config import Settings
from jdhp_api.core.errors import GrantTokenError
from jdhp_api.core.tokens import (
    ForensicKeys,
    GrantTokenIssuer,
    TileTokenSigner,
    derive_key,
    device_hash,
)


def test_sec_2_grant_token_round_trips_its_bindings(settings: Settings) -> None:
    issuer = GrantTokenIssuer(settings)
    token, expires = issuer.issue(
        session_id="s8abc",
        subject="user-1",
        work_public_id="w8xyz",
        grant_id="g8q",
        device_hash="d" * 64,
    )
    claims = issuer.verify(token)
    assert claims.session_id == "s8abc"
    assert claims.subject == "user-1"
    assert claims.work_public_id == "w8xyz"
    assert claims.grant_id == "g8q"
    assert claims.device_hash == "d" * 64
    assert claims.expires_at == expires.replace(microsecond=0)
    assert expires - dt.datetime.now(dt.UTC) <= dt.timedelta(
        seconds=settings.grant_token_ttl_seconds
    )


def test_sec_2_grant_token_rejects_tampering_expiry_and_other_keys(settings: Settings) -> None:
    issuer = GrantTokenIssuer(settings)
    token, _ = issuer.issue(
        session_id="s8abc",
        subject="user-1",
        work_public_id="w8xyz",
        grant_id=None,
        device_hash="d" * 64,
    )
    header, payload, signature = token.split(".")
    raw = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
    flipped = bytes([raw[0] ^ 0x01]) + raw[1:]  # one bit, deterministically
    tampered = base64.urlsafe_b64encode(flipped).rstrip(b"=").decode()
    with pytest.raises(GrantTokenError):
        issuer.verify(f"{header}.{payload}.{tampered}")
    with pytest.raises(GrantTokenError):
        issuer.verify("not-a-token")
    past = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=settings.grant_token_ttl_seconds + 60)
    expired, _ = issuer.issue(
        session_id="s8abc",
        subject="user-1",
        work_public_id="w8xyz",
        grant_id=None,
        device_hash="x",
        now=past,
    )
    with pytest.raises(GrantTokenError):
        issuer.verify(expired)
    other = GrantTokenIssuer(
        settings.model_copy(update={"token_signing_key": SecretStr("rotated-" + "z" * 40)})
    )
    with pytest.raises(GrantTokenError):
        other.verify(token)


def test_sec_10_tile_token_is_five_minutes_and_session_bound(settings: Settings) -> None:
    signer = TileTokenSigner(settings)
    token, expires = signer.issue("s8abc")
    assert signer.verify(token) == "s8abc"
    assert expires - dt.datetime.now(dt.UTC) <= dt.timedelta(seconds=300)
    with pytest.raises(GrantTokenError):
        signer.verify(token, now=expires + dt.timedelta(seconds=1))
    with pytest.raises(GrantTokenError):
        signer.verify(token.replace("s8abc", "s8abd"))
    with pytest.raises(GrantTokenError):
        signer.verify(token[:-3] + "xyz")
    with pytest.raises(GrantTokenError):
        signer.verify("t1.deadbeef.s8abc.1.sig")


def test_sec_11_forensic_key_is_per_session_and_sealed_at_rest(settings: Settings) -> None:
    forensic = ForensicKeys(settings)
    first, second = uuid.uuid4(), uuid.uuid4()
    key = forensic.session_key(first)
    assert len(key) == 32
    assert key != forensic.session_key(second)
    sealed = forensic.seal(key)
    assert key not in sealed
    assert forensic.open(sealed) == key
    assert forensic.seal(key) != sealed, "a fresh nonce every time"


def test_keys_derive_by_purpose_and_fingerprints_are_hashed(settings: Settings) -> None:
    secret = settings.token_signing_key.get_secret_value()
    assert derive_key(secret, "a") != derive_key(secret, "b")
    assert device_hash(" fp-1 ") == device_hash("fp-1")
    assert len(device_hash("fp-1")) == 64
    assert "fp-1" not in device_hash("fp-1")
