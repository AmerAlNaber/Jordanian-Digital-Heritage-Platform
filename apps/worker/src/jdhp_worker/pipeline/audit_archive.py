"""SEC-25: ship each day's audit events, signed, to the write-once archive bucket.

The bucket carries object lock in compliance mode and the application credential may only put
objects there, so a shipment can be added but never changed or removed. The shipment is the
same signed JSON an officer gets from the audit export, plus a manifest with the chain
boundaries; the shipment itself becomes an audit event, so the viewer shows what was shipped.
"""

from __future__ import annotations

import datetime as dt
import json
from typing import Any

from sqlalchemy import select

from jdhp_api.core import audit
from jdhp_api.core.db import RlsContext
from jdhp_api.core.orm import AuditOutcome, AuditSeverity
from jdhp_api.modules.audit.export import ExportSigner, build_export
from jdhp_api.modules.audit.models import AuditEvent
from jdhp_worker.runtime import Runtime

ACTOR = "jdhp-worker"


def archive_key(day: dt.date) -> str:
    return f"audit/{day:%Y}/{day:%Y-%m-%d}.json"


async def ship_day(rt: Runtime, day: dt.date) -> dict[str, Any]:
    """Export one UTC day of events to the archive bucket; nothing to ship is a quiet success."""
    start = dt.datetime.combine(day, dt.time.min, tzinfo=dt.UTC)
    end = start + dt.timedelta(days=1)
    settings = rt.settings
    async with rt.database.session(RlsContext.system()) as session:
        stmt = (
            select(AuditEvent)
            .where(AuditEvent.occurred_at >= start, AuditEvent.occurred_at < end)
            .order_by(AuditEvent.seq.asc())
        )
        events = (await session.scalars(stmt)).all()
        if not events:
            return {"day": day.isoformat(), "count": 0, "shipped": False}
        now = dt.datetime.now(dt.UTC)
        export = build_export(
            ExportSigner(settings),
            events,
            fmt="json",
            filters={"since": start.isoformat(), "until": end.isoformat()},
            now=now,
        )
        key = archive_key(day)
        manifest = {
            "day": day.isoformat(),
            "object": key,
            "count": len(events),
            "first_seq": events[0].seq,
            "last_seq": events[-1].seq,
            "first_prev_hash": events[0].prev_hash,
            "last_hash": events[-1].hash,
            "digest": export.digest,
            "signature": export.signature,
            "key_id": export.key_id,
            "shipped_at": now.isoformat(),
        }
        bucket = settings.bucket_audit_archive
        rt.store.put(bucket, key, export.body, content_type="application/json")
        rt.store.put(
            bucket,
            key + ".manifest.json",
            json.dumps(manifest, sort_keys=True).encode("utf-8"),
            content_type="application/json",
        )
        await audit.write(
            session,
            actor_id=ACTOR,
            actor_type="system",
            actor_roles=["system"],
            action="audit.shipped",
            resource_kind="audit_archive",
            resource_id=key,
            outcome=AuditOutcome.SUCCESS,
            severity=AuditSeverity.NOTICE,
            details={k: v for k, v in manifest.items() if k != "signature"},
        )
    return {**manifest, "shipped": True}


async def ship_previous_day(rt: Runtime) -> dict[str, Any]:
    yesterday = (dt.datetime.now(dt.UTC) - dt.timedelta(days=1)).date()
    return await ship_day(rt, yesterday)
