"""SEC-25: the daily shipment of audit events to the write-once archive."""

from __future__ import annotations

import datetime as dt
import hashlib
import json

from sqlalchemy import select

from jdhp_api.core import audit
from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.orm import AuditOutcome
from jdhp_api.core.storage import ObjectStore
from jdhp_api.modules.audit.export import ExportSigner
from jdhp_api.modules.audit.models import AuditEvent
from jdhp_worker.pipeline import audit_archive
from jdhp_worker.runtime import Runtime


async def test_sec_25_daily_shipment_is_signed_and_write_once(
    runtime: Runtime, app_database: Database, store: ObjectStore
) -> None:
    async with app_database.session(RlsContext.system()) as session:
        for n in range(3):
            await audit.write(
                session,
                actor_id=f"user-{n}",
                actor_type="user",
                actor_roles=["member"],
                action="reader.session_open",
                resource_kind="work",
                resource_id="w8test",
                outcome=AuditOutcome.SUCCESS,
                details={"n": n},
            )
        await session.commit()
    today = dt.datetime.now(dt.UTC).date()

    result = await audit_archive.ship_day(runtime, today)

    assert result["shipped"] is True
    assert result["count"] >= 3
    bucket = runtime.settings.bucket_audit_archive
    body = store.get(bucket, result["object"])
    manifest = json.loads(store.get(bucket, result["object"] + ".manifest.json"))
    document = json.loads(body)
    assert document["format"] == "jdhp-audit-export/1"
    assert [e["seq"] for e in document["events"]] == list(
        range(manifest["first_seq"], manifest["last_seq"] + 1)
    ), "the day is one contiguous chain segment"
    assert document["events"][0]["prev_hash"] == manifest["first_prev_hash"]
    assert document["events"][-1]["hash"] == manifest["last_hash"]
    assert (
        manifest["digest"]
        == "sha-256=" + __import__("base64").b64encode(hashlib.sha256(body).digest()).decode()
    )
    signer = ExportSigner(runtime.settings)
    assert manifest["key_id"] == signer.key_id
    assert ExportSigner.verify(signer.public_key_pem, body, manifest["signature"]) is True
    assert ExportSigner.verify(signer.public_key_pem, body + b" ", manifest["signature"]) is False

    async with app_database.session(RlsContext.system()) as session:
        shipped = (
            await session.scalars(select(AuditEvent).where(AuditEvent.action == "audit.shipped"))
        ).all()
    assert len(shipped) == 1
    assert shipped[0].resource_id == result["object"]
    assert "signature" not in shipped[0].details

    quiet = await audit_archive.ship_day(runtime, today - dt.timedelta(days=400))
    assert quiet == {
        "day": (today - dt.timedelta(days=400)).isoformat(),
        "count": 0,
        "shipped": False,
    }
