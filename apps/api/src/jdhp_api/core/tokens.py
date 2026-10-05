"""Reader credentials: grant and tile tokens, forensic session keys (SEC-2, SEC-10, SEC-11).

Every key here is derived with HKDF from one environment secret, so rotating that secret
rotates all of them and the ``kid`` on each token tells a verifier which generation signed it.

- Grant token: a compact JWT signed with Ed25519, bound to the reader session, the principal,
  the work, the grant and the device fingerprint hash. Ten minutes, refreshed by the heartbeat.
- Tile token: an HMAC-SHA256 token bound to the reader session, five minutes, carried in the
  tile URL and refreshed by the heartbeat.
- Forensic session key: derived from the forensic master key and the session id, stored only
  encrypted (AES-GCM under a key derived from the field encryption key), so a leaked page can
  be traced to the session without the key ever sitting in clear in the database.
"""

from __future__ import annotations

import base64
import dataclasses
import datetime as dt
import hashlib
import hmac
import os
import uuid

import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from jdhp_api.core.config import Settings
from jdhp_api.core.errors import GrantTokenError

GRANT_TOKEN_ISSUER = "jdhp"  # noqa: S105  # nosec B105  # an issuer name, not a secret
GRANT_TOKEN_AUDIENCE = "jdhp-reader"  # noqa: S105  # nosec B105  # an audience, not a secret
TILE_TOKEN_VERSION = "t1"  # noqa: S105  # nosec B105  # a format version, not a secret
NONCE_BYTES = 12
TILE_SIGNATURE_BYTES = 32


def derive_key(secret: str, info: str, length: int = 32) -> bytes:
    """HKDF-SHA256 over the environment secret, separated by purpose with ``info``."""
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=None, info=info.encode()).derive(
        secret.encode()
    )


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def device_hash(fingerprint: str) -> str:
    """The stored and token-bound form of a device fingerprint: never the fingerprint itself."""
    return hashlib.sha256(fingerprint.strip().encode()).hexdigest()


@dataclasses.dataclass(frozen=True, slots=True)
class GrantClaims:
    session_id: str
    subject: str
    work_public_id: str
    grant_id: str | None
    device_hash: str
    expires_at: dt.datetime
    token_id: str


class GrantTokenIssuer:
    """Issues and verifies grant tokens. The key pair derives from the token signing key."""

    def __init__(self, settings: Settings) -> None:
        seed = derive_key(settings.token_signing_key.get_secret_value(), "jdhp grant token v1")
        self._private = Ed25519PrivateKey.from_private_bytes(seed)
        public = self._private.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        self.kid = hashlib.sha256(public).hexdigest()[:16]
        self._public_pem = self._private.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        self._private_pem = self._private.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
        self.ttl_seconds = settings.grant_token_ttl_seconds

    def issue(
        self,
        *,
        session_id: str,
        subject: str,
        work_public_id: str,
        grant_id: str | None,
        device_hash: str,
        now: dt.datetime | None = None,
    ) -> tuple[str, dt.datetime]:
        issued = now or dt.datetime.now(dt.UTC)
        expires = issued + dt.timedelta(seconds=self.ttl_seconds)
        claims = {
            "iss": GRANT_TOKEN_ISSUER,
            "aud": GRANT_TOKEN_AUDIENCE,
            "sub": subject,
            "sid": session_id,
            "wrk": work_public_id,
            "gid": grant_id,
            "dev": device_hash,
            "iat": int(issued.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": uuid.uuid4().hex,
        }
        token = jwt.encode(claims, self._private_pem, algorithm="EdDSA", headers={"kid": self.kid})
        return token, expires

    def verify(self, token: str) -> GrantClaims:
        try:
            header = jwt.get_unverified_header(token)
            if header.get("kid") != self.kid:
                raise GrantTokenError
            claims = jwt.decode(
                token,
                self._public_pem,
                algorithms=["EdDSA"],
                audience=GRANT_TOKEN_AUDIENCE,
                issuer=GRANT_TOKEN_ISSUER,
                options={"require": ["exp", "iat", "sub", "sid", "wrk", "dev", "jti"]},
            )
            return GrantClaims(
                session_id=str(claims["sid"]),
                subject=str(claims["sub"]),
                work_public_id=str(claims["wrk"]),
                grant_id=str(claims["gid"]) if claims.get("gid") else None,
                device_hash=str(claims["dev"]),
                expires_at=dt.datetime.fromtimestamp(int(claims["exp"]), tz=dt.UTC),
                token_id=str(claims["jti"]),
            )
        except GrantTokenError:
            raise
        except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
            raise GrantTokenError from exc


class TileTokenSigner:
    """Five-minute HMAC tokens bound to one reader session (SEC-10)."""

    def __init__(self, settings: Settings) -> None:
        self._key = derive_key(settings.token_signing_key.get_secret_value(), "jdhp tile token v1")
        self.kid = hashlib.sha256(self._key).hexdigest()[:8]
        self.ttl_seconds = settings.tile_token_ttl_seconds

    def _signature(self, payload: str) -> str:
        digest = hmac.new(self._key, payload.encode(), hashlib.sha256).digest()
        return _b64(digest[:TILE_SIGNATURE_BYTES])

    def issue(self, session_id: str, now: dt.datetime | None = None) -> tuple[str, dt.datetime]:
        issued = now or dt.datetime.now(dt.UTC)
        expires = issued + dt.timedelta(seconds=self.ttl_seconds)
        payload = f"{TILE_TOKEN_VERSION}.{self.kid}.{session_id}.{int(expires.timestamp())}"
        return f"{payload}.{self._signature(payload)}", expires

    def verify(self, token: str, now: dt.datetime | None = None) -> str:
        """The public name of the session the token was issued for, or ``GrantTokenError``."""
        parts = token.split(".")
        if len(parts) != 5 or parts[0] != TILE_TOKEN_VERSION or parts[1] != self.kid:
            raise GrantTokenError
        payload = ".".join(parts[:4])
        if not hmac.compare_digest(self._signature(payload), parts[4]):
            raise GrantTokenError
        try:
            expires = int(parts[3])
        except ValueError as exc:
            raise GrantTokenError from exc
        current = int((now or dt.datetime.now(dt.UTC)).timestamp())
        if current >= expires or not parts[2]:
            raise GrantTokenError
        return parts[2]


class ForensicKeys:
    """Per-session forensic keys and their sealed storage form (SEC-11)."""

    def __init__(self, settings: Settings) -> None:
        self._master = settings.forensic_master_key.get_secret_value()
        self._seal_key = derive_key(
            settings.field_encryption_key.get_secret_value(), "jdhp field encryption v1"
        )

    def session_key(self, session_id: uuid.UUID) -> bytes:
        return derive_key(self._master, f"jdhp forensic session {session_id}")

    def seal(self, key: bytes) -> bytes:
        nonce = os.urandom(NONCE_BYTES)
        return nonce + AESGCM(self._seal_key).encrypt(nonce, key, None)

    def open(self, sealed: bytes) -> bytes:
        nonce, ciphertext = sealed[:NONCE_BYTES], sealed[NONCE_BYTES:]
        return AESGCM(self._seal_key).decrypt(nonce, ciphertext, None)
