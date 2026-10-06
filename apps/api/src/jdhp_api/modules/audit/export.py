"""Signed exports of the audit log (ADM-5) and the bytes the daily shipment stores (SEC-25).

The same events render to the same bytes, the bytes are signed with an Ed25519 key derived
from the token signing secret, and every record carries its chain hashes, so a segment can be
checked offline against the public key the API publishes.
"""

from __future__ import annotations

import base64
import csv
import dataclasses
import datetime as dt
import hashlib
import io
import json
from collections.abc import Mapping, Sequence
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from jdhp_api.core.config import Settings
from jdhp_api.core.tokens import derive_key
from jdhp_api.modules.audit.models import AuditEvent

EXPORT_FORMAT = "jdhp-audit-export/1"
EXPORT_MAX_ROWS = 20_000
CSV_COLUMNS = (
    "seq",
    "occurred_at",
    "actor_id",
    "actor_type",
    "actor_roles",
    "action",
    "resource_kind",
    "resource_id",
    "outcome",
    "severity",
    "ip",
    "request_id",
    "details",
    "prev_hash",
    "hash",
)
MEDIA_TYPES = {"csv": "text/csv; charset=utf-8", "json": "application/json"}


class ExportSigner:
    """Ed25519 over the export bytes; the key pair derives from the token signing secret."""

    def __init__(self, settings: Settings) -> None:
        seed = derive_key(settings.token_signing_key.get_secret_value(), "jdhp audit export v1")
        self._private = Ed25519PrivateKey.from_private_bytes(seed)
        public = self._private.public_key()
        raw = public.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        self.key_id = hashlib.sha256(raw).hexdigest()[:16]
        self.public_key_pem = public.public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode()

    def sign(self, data: bytes) -> str:
        return base64.b64encode(self._private.sign(data)).decode()

    @staticmethod
    def verify(public_key_pem: str, data: bytes, signature: str) -> bool:
        key = serialization.load_pem_public_key(public_key_pem.encode())
        if not isinstance(key, Ed25519PublicKey):
            return False
        try:
            key.verify(base64.b64decode(signature), data)
        except (InvalidSignature, ValueError):
            return False
        return True


def event_record(event: AuditEvent) -> dict[str, Any]:
    return {
        "seq": event.seq,
        "occurred_at": event.occurred_at.isoformat(),
        "actor_id": event.actor_id,
        "actor_type": event.actor_type,
        "actor_roles": sorted(event.actor_roles),
        "action": event.action,
        "resource_kind": event.resource_kind,
        "resource_id": event.resource_id,
        "outcome": str(event.outcome),
        "severity": str(event.severity),
        "ip": event.ip,
        "request_id": event.request_id,
        "details": event.details,
        "prev_hash": event.prev_hash,
        "hash": event.hash,
    }


def render_csv(events: Sequence[AuditEvent]) -> bytes:
    """UTF-8 with a byte-order mark so spreadsheet tools read Arabic correctly."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for event in events:
        record = event_record(event)
        record["actor_roles"] = ";".join(record["actor_roles"])
        record["details"] = json.dumps(record["details"], ensure_ascii=False, sort_keys=True)
        writer.writerow("" if record[c] is None else record[c] for c in CSV_COLUMNS)
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def render_json(
    events: Sequence[AuditEvent], *, filters: Mapping[str, Any], exported_at: dt.datetime
) -> bytes:
    document = {
        "format": EXPORT_FORMAT,
        "exported_at": exported_at.isoformat(),
        "filters": {k: v for k, v in filters.items() if v is not None},
        "count": len(events),
        "events": [event_record(e) for e in events],
    }
    return json.dumps(document, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")


def digest_of(data: bytes) -> str:
    return "sha-256=" + base64.b64encode(hashlib.sha256(data).digest()).decode()


@dataclasses.dataclass(frozen=True)
class SignedExport:
    body: bytes
    media_type: str
    filename: str
    digest: str
    signature: str
    key_id: str

    @property
    def headers(self) -> dict[str, str]:
        return {
            "Content-Disposition": f'attachment; filename="{self.filename}"',
            "Digest": self.digest,
            "X-Jdhp-Signature": f"ed25519={self.signature}",
            "X-Jdhp-Signature-Key": self.key_id,
            "Cache-Control": "private, no-store",
        }


def build_export(
    signer: ExportSigner,
    events: Sequence[AuditEvent],
    *,
    fmt: str,
    filters: Mapping[str, Any],
    now: dt.datetime,
) -> SignedExport:
    if fmt not in MEDIA_TYPES:
        raise ValueError(f"unknown export format {fmt!r}")
    body = (
        render_csv(events)
        if fmt == "csv"
        else render_json(events, filters=filters, exported_at=now)
    )
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    return SignedExport(
        body=body,
        media_type=MEDIA_TYPES[fmt],
        filename=f"jdhp-audit-{stamp}.{fmt}",
        digest=digest_of(body),
        signature=signer.sign(body),
        key_id=signer.key_id,
    )
