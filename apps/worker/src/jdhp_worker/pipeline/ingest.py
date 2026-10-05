"""Ingest: validate staged masters, write them once to preservation, package METS, fan out."""

from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select

from jdhp_api.core import storage
from jdhp_api.core.db import RlsContext
from jdhp_api.core.orm import DigitalObjectState, FixityStatus, IntakeState, PremisEventType
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.ingest import service as ingest_service
from jdhp_api.modules.ingest.models import DigitalObject, IntakeBatch, Page
from jdhp_metadata.checksums import ChecksumEntry, format_manifest
from jdhp_metadata.mets import MetsFile, MetsPackage, build_mets
from jdhp_worker.pipeline.validation import MasterValidationError, validate_master
from jdhp_worker.runtime import Runtime

AGENT = "jdhp-worker ingest"


async def package_batch(rt: Runtime, batch_id: uuid.UUID) -> dict[str, object]:
    settings = rt.settings
    async with rt.database.session(RlsContext.system()) as session:
        batch = await session.get(IntakeBatch, batch_id)
        if batch is None or batch.digital_object_id is None or batch.work_id is None:
            return {"batch": str(batch_id), "status": "missing"}
        if batch.state not in {IntakeState.RECEIVED, IntakeState.FAILED}:
            return {"batch": str(batch_id), "status": str(batch.state)}
        digital_object = await session.get(DigitalObject, batch.digital_object_id)
        work = await session.get(Work, batch.work_id)
        if digital_object is None or work is None:
            return {"batch": str(batch_id), "status": "missing"}
        pages = list(
            (
                await session.scalars(
                    select(Page)
                    .where(Page.digital_object_id == digital_object.id)
                    .order_by(Page.seq)
                )
            ).all()
        )
        await ingest_service.mark_batch_state(session, batch.id, IntakeState.VALIDATING)
        staging_prefix = batch.staging_prefix
        manifest_pages = {int(p["seq"]): p for p in batch.manifest.get("pages", [])}
        work_id, do_id = work.id, digital_object.id

    mets_files: list[MetsFile] = []
    checksums: list[ChecksumEntry] = []
    for page in pages:
        entry = manifest_pages.get(page.seq, {})
        staged_key = f"{staging_prefix}/{entry.get('filename', f'{page.seq:04d}.tif')}"
        try:
            data = rt.store.get(settings.bucket_uploads, staged_key)
            info = validate_master(
                data,
                expected_sha256=str(entry.get("sha256") or page.master_sha256 or ""),
                min_ppi=settings.master_min_ppi,
                max_bytes=settings.max_master_bytes,
            )
        except (MasterValidationError, Exception) as exc:
            reason = (
                f"page {page.seq}: {exc}"
                if isinstance(exc, MasterValidationError)
                else f"page {page.seq}: {exc.__class__.__name__}"
            )
            async with rt.database.session(RlsContext.system()) as session:
                await ingest_service.mark_batch_state(
                    session, batch_id, IntakeState.FAILED, error=reason
                )
                await ingest_service.write_premis(
                    session,
                    do_id,
                    event_type=PremisEventType.INGEST,
                    outcome="fail",
                    agent=AGENT,
                    detail={"reason": reason},
                )
            return {"batch": str(batch_id), "status": "failed", "reason": reason}
        key = storage.master_key(work_id, do_id, page.seq)
        if not rt.ingest_store.exists(settings.bucket_preservation, key):
            rt.ingest_store.put(settings.bucket_preservation, key, data, content_type="image/tiff")
        async with rt.database.session(RlsContext.system()) as session:
            await ingest_service.record_master(
                session,
                page.id,
                master_key=key,
                sha256=info.sha256,
                width_px=info.width,
                height_px=info.height,
            )
        mets_files.append(
            MetsFile(seq=page.seq, key=key, sha256=info.sha256, size=info.size, label=page.label)
        )
        checksums.append(ChecksumEntry(info.sha256, f"master/{page.seq:04d}.tif"))

    async with rt.database.session(RlsContext.system()) as session:
        work_row = await session.get(Work, work_id)
        title = work_row.title_ar if work_row else None
        public_id = work_row.public_id if work_row else ""
    package = MetsPackage(
        work_public_id=public_id,
        digital_object_id=str(do_id),
        created=dt.datetime.now(dt.UTC),
        files=tuple(mets_files),
        title=title,
    )
    mets_key = storage.mets_key(work_id, do_id)
    rt.ingest_store.put(
        settings.bucket_preservation, mets_key, build_mets(package), content_type="application/xml"
    )
    rt.ingest_store.put(
        settings.bucket_preservation,
        storage.checksums_key(work_id, do_id),
        format_manifest(checksums).encode("utf-8"),
        content_type="text/plain",
    )
    async with rt.database.session(RlsContext.system()) as session:
        await ingest_service.set_digital_object_state(
            session, do_id, DigitalObjectState.PROCESSING, mets_key=mets_key, fixity=FixityStatus.OK
        )
        await ingest_service.write_premis(
            session,
            do_id,
            event_type=PremisEventType.INGEST,
            outcome="success",
            agent=AGENT,
            detail={"pages": len(pages), "mets": mets_key},
        )
    for page in pages:
        rt.send("jdhp.derivatives.generate", page_id=str(page.id))
        rt.send("jdhp.ocr.recognize", page_id=str(page.id))
    return {"batch": str(batch_id), "status": "packaged", "pages": len(pages)}
