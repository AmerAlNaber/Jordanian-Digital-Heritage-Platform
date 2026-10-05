"""The print render task (RDR-4): the worker role renders a queued job to the exports bucket."""

from __future__ import annotations

import datetime as dt
import io
import uuid
from typing import Any

import pyvips
from pypdf import PdfReader
from sqlalchemy import select

from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.ids import mint_name
from jdhp_api.core.orm import (
    AccessClass,
    DigitalObjectState,
    GrantSource,
    PageType,
    PrintJobState,
    PublishState,
    ReaderSessionState,
    UserRole,
)
from jdhp_api.core.storage import ObjectStore
from jdhp_api.core.tokens import ForensicKeys, device_hash
from jdhp_api.modules.access.models import Grant
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.identity.models import User
from jdhp_api.modules.ingest.models import DigitalObject, Page
from jdhp_api.modules.reader.models import PrintJob, ReaderSession
from jdhp_worker.inline import run_inline
from jdhp_worker.runtime import Runtime
from jdhp_worker.settings import WorkerSettings

PAGE_W, PAGE_H = 600, 900


def _scan(seq: int) -> bytes:
    base = pyvips.Image.black(PAGE_W, PAGE_H, bands=3).new_from_image([230, 220, 200])
    band = pyvips.Image.black(PAGE_W - 100, 40, bands=3).new_from_image([30, 30, 30])
    image = base.insert(band, 50, 100 + seq * 50).copy(interpretation="srgb")
    return bytes(image.jp2ksave_buffer(Q=80, tile_width=256, tile_height=256))


async def _seed(
    admin_database: Database, store: ObjectStore, settings: WorkerSettings
) -> tuple[uuid.UUID, str]:
    now = dt.datetime.now(dt.UTC)
    async with admin_database.session(RlsContext.system()) as session:
        user = User(
            keycloak_sub="printer-1", email="p@example.test", display_name="P", role=UserRole.MEMBER
        )
        work = Work(
            public_id=mint_name("w8"),
            title_ar="كتاب للطباعة",
            access_class=AccessClass.REGISTERED,
            publish_state=PublishState.PUBLISHED,
            published_at=now,
        )
        session.add_all([user, work])
        await session.flush()
        digital_object = DigitalObject(
            work_id=work.id, page_count=3, state=DigitalObjectState.READY
        )
        session.add(digital_object)
        await session.flush()
        for seq in range(1, 4):
            key = f"{work.id}/{digital_object.id}/jp2/{seq:04d}.jp2"
            store.put(settings.bucket_access, key, _scan(seq), content_type="image/jp2")
            session.add(
                Page(
                    digital_object_id=digital_object.id,
                    work_id=work.id,
                    seq=seq,
                    label=str(seq),
                    page_type=PageType.TEXT,
                    derivative_key=key,
                    width_px=PAGE_W,
                    height_px=PAGE_H,
                )
            )
        grant = Grant(
            user_id=user.id,
            work_id=work.id,
            starts_at=now - dt.timedelta(minutes=1),
            ends_at=now + dt.timedelta(days=1),
            device_limit=2,
            source=GrantSource.ACCESS_CLASS,
            print_quota=20,
        )
        session.add(grant)
        await session.flush()
        keys = ForensicKeys(settings)
        reader_id = uuid.uuid4()
        reader = ReaderSession(
            id=reader_id,
            user_id=user.id,
            work_id=work.id,
            grant_id=grant.id,
            device_hash=device_hash("fingerprint-print"),
            forensic_key_encrypted=keys.seal(keys.session_key(reader_id)),
            state=ReaderSessionState.ACTIVE,
            last_seen_at=now,
            idle_expires_at=now + dt.timedelta(minutes=30),
            hard_expires_at=now + dt.timedelta(days=1),
        )
        session.add(reader)
        await session.flush()
        job = PrintJob(
            reader_session_id=reader.id,
            grant_id=grant.id,
            user_id=user.id,
            work_id=work.id,
            pages=[1, 3],
            state=PrintJobState.QUEUED,
        )
        session.add(job)
        await session.flush()
        return job.id, job.public_id


def test_rdr_4_worker_renders_a_queued_print_job(
    runtime: Runtime, store: ObjectStore, admin_database: Database, settings: WorkerSettings
) -> None:
    job_id, job_public_id = runtime.run(_seed(admin_database, store, settings))
    results = run_inline(runtime, "jdhp.print.render", job_id=str(job_id))
    assert results[0]["status"] == "ready"
    assert results[0]["pages"] == 2

    async def state() -> Any:
        async with admin_database.session(RlsContext.system()) as session:
            return (await session.scalars(select(PrintJob).where(PrintJob.id == job_id))).one()

    job = runtime.run(state())
    assert job.state == PrintJobState.READY
    assert job.export_key == f"prints/{job_public_id}.pdf"
    pdf = PdfReader(io.BytesIO(store.get(settings.bucket_exports, job.export_key)))
    assert len(pdf.pages) == 2
    assert float(pdf.pages[0].mediabox.width) == PAGE_W * 72 / settings.print_ppi

    # Running the task again is a no-op: the job is no longer queued.
    again = run_inline(runtime, "jdhp.print.render", job_id=str(job_id))
    assert again[0]["status"] == "ready"
