"""Fixity: verify masters against the recorded SHA-256; a mismatch opens an incident and freezes."""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import select

from jdhp_api.core.db import RlsContext
from jdhp_api.core.orm import DigitalObjectState, FixityStatus, IncidentKind, PremisEventType
from jdhp_api.modules.ingest import service as ingest_service
from jdhp_api.modules.ingest.models import DigitalObject, Incident, Page
from jdhp_worker.runtime import Runtime

AGENT = "jdhp-worker fixity"


async def verify_digital_object(rt: Runtime, digital_object_id: uuid.UUID) -> dict[str, object]:
    settings = rt.settings
    async with rt.database.session(RlsContext.system()) as session:
        pages = list(
            (
                await session.scalars(
                    select(Page)
                    .where(Page.digital_object_id == digital_object_id)
                    .order_by(Page.seq)
                )
            ).all()
        )
        checks = [
            (p.id, p.seq, p.master_key, p.master_sha256, p.derivative_key, p.derivative_sha256)
            for p in pages
        ]
    mismatches: list[dict[str, object]] = []
    for _page_id, seq, master_key, master_sha, derivative_key, derivative_sha in checks:
        if master_key and master_sha:
            actual = hashlib.sha256(
                rt.ingest_store.get(settings.bucket_preservation, master_key)
            ).hexdigest()
            if actual != master_sha:
                mismatches.append(
                    {"seq": seq, "object": "master", "expected": master_sha, "actual": actual}
                )
        if derivative_key and derivative_sha:
            actual = hashlib.sha256(
                rt.store.get(settings.bucket_access, derivative_key)
            ).hexdigest()
            if actual != derivative_sha:
                mismatches.append(
                    {
                        "seq": seq,
                        "object": "derivative",
                        "expected": derivative_sha,
                        "actual": actual,
                    }
                )
    async with rt.database.session(RlsContext.system()) as session:
        if mismatches:
            session.add(
                Incident(
                    kind=IncidentKind.FIXITY_MISMATCH,
                    severity="high",
                    digital_object_id=digital_object_id,
                    detail={"mismatches": mismatches},
                )
            )
            await ingest_service.set_digital_object_state(
                session,
                digital_object_id,
                DigitalObjectState.FROZEN,
                fixity=FixityStatus.MISMATCH,
                frozen_reason=f"fixity mismatch on {len(mismatches)} object(s)",
            )
            await ingest_service.write_premis(
                session,
                digital_object_id,
                event_type=PremisEventType.FIXITY_CHECK,
                outcome="fail",
                agent=AGENT,
                detail={"mismatches": mismatches},
            )
        else:
            digital_object = await session.get(DigitalObject, digital_object_id)
            if digital_object is not None:
                await ingest_service.set_digital_object_state(
                    session, digital_object_id, digital_object.state, fixity=FixityStatus.OK
                )
            await ingest_service.write_premis(
                session,
                digital_object_id,
                event_type=PremisEventType.FIXITY_CHECK,
                outcome="success",
                agent=AGENT,
                detail={"pages": len(checks)},
            )
    return {"digital_object": str(digital_object_id), "mismatches": len(mismatches)}


async def sweep(rt: Runtime) -> dict[str, object]:
    async with rt.database.session(RlsContext.system()) as session:
        ids = list(
            (
                await session.scalars(
                    select(DigitalObject.id).where(DigitalObject.state == DigitalObjectState.READY)
                )
            ).all()
        )
    for digital_object_id in ids:
        rt.send("jdhp.fixity.verify", digital_object_id=str(digital_object_id))
    return {"scheduled": len(ids)}
