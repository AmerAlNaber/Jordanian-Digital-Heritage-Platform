"""Print (RDR-4, SEC-11, SEC-15): quota, page range, marks, the single-use link, audit."""

from __future__ import annotations

import datetime as dt
import io
import os
import re
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
import pytest
import pytest_asyncio
import pyvips
from fastapi import FastAPI
from moto import mock_aws
from pypdf import PdfReader
from sqlalchemy import select

from jdhp_api.core.auth import TokenVerifier
from jdhp_api.core.config import Settings
from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.orm import AccessClass
from jdhp_api.core.storage import ObjectStore
from jdhp_api.core.tasks import RecordingDispatcher
from jdhp_api.main import create_app
from jdhp_api.modules.audit.models import AuditEvent
from jdhp_api.modules.ingest.models import Page
from jdhp_api.modules.reader import forensic, printing
from jdhp_api.modules.reader.models import PrintJob, ReaderSession
from jdhp_api.modules.reader.pdf import PdfImage, build_pdf, points
from tests.factories import make_grant, make_user, make_work

Headers = Callable[..., dict[str, str]]
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
FINGERPRINT = "device-fingerprint-alpha"
PAGE_W, PAGE_H = 945, 1418


def _page_image(seq: int) -> pyvips.Image:
    base = pyvips.Image.black(PAGE_W, PAGE_H, bands=3).new_from_image([236, 226, 206])
    band = pyvips.Image.black(PAGE_W - 200, 60, bands=3).new_from_image([40, 30, 20])
    return base.insert(band, 100, 200 + (seq * 37) % 900).copy(interpretation="srgb")


@pytest.fixture
def access_store(settings: Settings) -> Any:
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
    with mock_aws():
        store = ObjectStore(
            endpoint_url=None, region=settings.s3_region, access_key="testing", secret_key="testing"
        )
        store.ensure_bucket(settings.bucket_access)
        store.ensure_bucket(settings.bucket_exports)
        yield store


@pytest_asyncio.fixture
async def app(
    settings: Settings,
    database: Database,
    dispatcher: RecordingDispatcher,
    access_store: ObjectStore,
) -> AsyncIterator[FastAPI]:
    application = create_app(
        settings, database=database, token_verifier=TokenVerifier(settings), store=access_store
    )
    application.state.dispatcher = dispatcher
    async with application.router.lifespan_context(application):
        yield application


async def _seed_derivatives(
    admin_database: Database, store: ObjectStore, settings: Settings, work_id: Any
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        pages = (await session.scalars(select(Page).where(Page.work_id == work_id))).all()
        for page in pages:
            key = f"{work_id}/{page.digital_object_id}/jp2/{page.seq:04d}.jp2"
            data = _page_image(page.seq).jp2ksave_buffer(Q=80, tile_width=512, tile_height=512)
            store.put(settings.bucket_access, key, bytes(data), content_type="image/jp2")
            page.derivative_key = key
        await session.flush()


async def _open(
    client: httpx.AsyncClient, work_public_id: str, headers: dict[str, str] | None = None
) -> dict[str, Any]:
    response = await client.post(
        "/reader/sessions",
        json={"work": work_public_id, "device_fingerprint": FINGERPRINT},
        headers=headers or {},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _grant_header(opened: dict[str, Any]) -> dict[str, str]:
    return {"X-Jdhp-Grant": opened["tokens"]["grant_token"]}


async def _print(
    client: httpx.AsyncClient,
    opened: dict[str, Any],
    pages: list[int],
    headers: dict[str, str] | None = None,
) -> httpx.Response:
    """Print needs both credentials: the signed-in principal and the session's grant token."""
    return await client.post(
        f"/reader/sessions/{opened['public_id']}/print",
        json={"pages": pages},
        headers={**_grant_header(opened), **(headers or {})},
    )


async def _render(app: FastAPI, store: ObjectStore, job_public_id: str) -> dict[str, object]:
    async with app.state.database.session(RlsContext.system()) as session:
        job = (
            await session.scalars(select(PrintJob).where(PrintJob.public_id == job_public_id))
        ).one()
        job_id = job.id
    return await printing.render_print(
        database=app.state.database,
        store=store,
        settings=app.state.settings,
        forensic_keys=app.state.reader.forensic,
        job_id=job_id,
    )


async def _audit_actions(admin_database: Database, prefix: str) -> list[AuditEvent]:
    async with admin_database.session(RlsContext.system()) as session:
        rows = await session.scalars(
            select(AuditEvent).where(AuditEvent.action.like(f"{prefix}%")).order_by(AuditEvent.seq)
        )
        return list(rows.all())


# --- The whole path: request, render, link, download ------------------------------------------


async def test_rdr_4_member_prints_two_pages_as_a_marked_low_resolution_pdf(
    client: httpx.AsyncClient,
    admin_database: Database,
    access_store: ObjectStore,
    settings: Settings,
    auth: Headers,
    app: FastAPI,
    dispatcher: RecordingDispatcher,
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=12)
    await _seed_derivatives(admin_database, access_store, settings, work.id)
    headers = auth("maha", ["member"])
    opened = await _open(client, work.public_id, headers)

    requested = await _print(client, opened, [2, 1, 2], headers)
    assert requested.status_code == 202, requested.text
    job = requested.json()
    assert job["public_id"].startswith("p8")
    assert job["state"] == "queued"
    assert job["pages"] == [1, 2]
    assert job["quota_remaining"] == settings.print_quota_default_pages - 2
    assert job["work"] == work.public_id
    assert job["grant"] == opened["grant"]
    assert not UUID_RE.search(requested.text)
    task_name, kwargs = dispatcher.sent[-1]
    assert task_name == "jdhp.print.render"
    async with admin_database.session(RlsContext.system()) as session:
        row = (
            await session.scalars(select(PrintJob).where(PrintJob.public_id == job["public_id"]))
        ).one()
        reader = (
            await session.scalars(
                select(ReaderSession).where(ReaderSession.public_id == opened["public_id"])
            )
        ).one()
        reader_id = row.reader_session_id
    assert kwargs == {"job_id": str(row.id)}
    assert reader_id == reader.id

    status = await client.get(f"/reader/prints/{job['public_id']}", headers=headers)
    assert status.status_code == 200
    assert status.json()["state"] == "queued"
    too_early = await client.post(f"/reader/prints/{job['public_id']}/link", headers=headers)
    assert too_early.status_code == 409
    assert too_early.json()["code"] == "print_not_ready"

    result = await _render(app, access_store, job["public_id"])
    assert result["status"] == "ready"
    status = await client.get(f"/reader/prints/{job['public_id']}", headers=headers)
    assert status.json()["state"] == "ready"
    assert status.json()["rendered_at"] is not None

    link = await client.post(f"/reader/prints/{job['public_id']}/link", headers=headers)
    assert link.status_code == 200, link.text
    url = link.json()["url"]
    assert f"/reader/prints/{job['public_id']}/file?t=" in url
    expires = dt.datetime.fromisoformat(link.json()["expires_at"])
    assert expires - dt.datetime.now(dt.UTC) <= dt.timedelta(minutes=15)

    # The browser follows the link with no Authorization header: the token is the credential.
    path = url.split("/api", 1)[1] if "/api/" in url else url.split("http://localhost:8080")[1]
    download = await client.get(path)
    assert download.status_code == 200, download.text
    assert download.headers["content-type"] == "application/pdf"
    assert download.headers["content-disposition"].startswith("attachment;")
    assert download.headers["cache-control"] == "private, no-store"

    pdf = PdfReader(io.BytesIO(download.content))
    assert len(pdf.pages) == 2
    assert pdf.metadata is not None
    assert pdf.metadata.title == work.title_ar
    page = pdf.pages[0]
    assert float(page.mediabox.width) == pytest.approx(points(PAGE_W, settings.print_ppi))
    assert float(page.mediabox.height) == pytest.approx(points(PAGE_H, settings.print_ppi))
    xobject = page["/Resources"]["/XObject"]["/Im0"]
    assert xobject["/Filter"] == "/DCTDecode"
    assert xobject["/Width"] == PAGE_W
    assert xobject["/Height"] == PAGE_H
    jpeg = xobject.get_data()
    rendered = pyvips.Image.new_from_buffer(jpeg, "")
    assert (rendered.width, rendered.height) == (PAGE_W, PAGE_H)
    # SEC-11: the visible mark changed the page, and the session's forensic mark is detectable.
    difference = (rendered - _page_image(1)).abs().avg()
    assert difference > 1.0, difference
    key = app.state.reader.forensic.session_key(reader_id)
    assert forensic.detect(rendered, key).present
    assert not forensic.detect(rendered, b"another key").present
    assert not forensic.detect(_page_image(1), key).present

    after = await client.get(f"/reader/prints/{job['public_id']}", headers=headers)
    assert after.json()["state"] == "downloaded"
    assert after.json()["downloaded_at"] is not None
    assert access_store.head(settings.bucket_exports, f"prints/{job['public_id']}.pdf") is None

    events = await _audit_actions(admin_database, "print.")
    actions = [event.action for event in events]
    assert actions == ["print.request", "print.render", "print.link", "print.download"]
    assert events[0].details["pages"] == [1, 2]
    assert events[0].details["job"] == job["public_id"]
    assert events[3].details["pages"] == [1, 2]


async def test_sec_15_download_url_single_use(
    client: httpx.AsyncClient,
    admin_database: Database,
    access_store: ObjectStore,
    settings: Settings,
    auth: Headers,
    app: FastAPI,
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=4)
    await _seed_derivatives(admin_database, access_store, settings, work.id)
    headers = auth("maha", ["member"])
    opened = await _open(client, work.public_id, headers)
    job = (await _print(client, opened, [1], headers)).json()
    await _render(app, access_store, job["public_id"])
    file_path = f"/reader/prints/{job['public_id']}/file"

    # No token, a wrong token, and the owner's own credentials do not open the file.
    assert (await client.get(file_path)).status_code == 403
    assert (await client.get(file_path, params={"t": "x" * 43})).status_code == 403
    assert (await client.get(file_path, headers=headers)).status_code == 403

    link = (await client.post(f"/reader/prints/{job['public_id']}/link", headers=headers)).json()
    token = link["url"].split("?t=", 1)[1]
    first = await client.get(file_path, params={"t": token})
    assert first.status_code == 200
    second = await client.get(file_path, params={"t": token})
    assert second.status_code == 403
    # Nor can a new link be minted once the file was delivered.
    again = await client.post(f"/reader/prints/{job['public_id']}/link", headers=headers)
    assert again.status_code == 409

    # An expired link is refused even with the right token.
    other = (await _print(client, opened, [2], headers)).json()
    await _render(app, access_store, other["public_id"])
    link = (await client.post(f"/reader/prints/{other['public_id']}/link", headers=headers)).json()
    token = link["url"].split("?t=", 1)[1]
    async with admin_database.session(RlsContext.system()) as session:
        row = (
            await session.scalars(select(PrintJob).where(PrintJob.public_id == other["public_id"]))
        ).one()
        row.token_expires_at = dt.datetime.now(dt.UTC) - dt.timedelta(seconds=1)
        await session.flush()
    expired = await client.get(f"/reader/prints/{other['public_id']}/file", params={"t": token})
    assert expired.status_code == 403
    # A fresh link works again while the job is still ready.
    link = (await client.post(f"/reader/prints/{other['public_id']}/link", headers=headers)).json()
    token = link["url"].split("?t=", 1)[1]
    assert (
        await client.get(f"/reader/prints/{other['public_id']}/file", params={"t": token})
    ).status_code == 200


async def test_rdr_4_print_quota_enforced(
    client: httpx.AsyncClient,
    admin_database: Database,
    access_store: ObjectStore,
    settings: Settings,
    auth: Headers,
    app: FastAPI,
) -> None:
    quota = settings.print_quota_default_pages
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=quota + 5)
    await _seed_derivatives(admin_database, access_store, settings, work.id)
    headers = auth("maha", ["member"])
    opened = await _open(client, work.public_id, headers)

    over = await _print(client, opened, list(range(1, quota + 2)), headers)
    assert over.status_code == 403
    assert over.json()["code"] == "print_quota_exceeded"
    assert over.json()["quota_remaining"] == quota

    first = await _print(client, opened, list(range(1, quota - 1)), headers)
    assert first.status_code == 202
    assert first.json()["quota_remaining"] == 2
    denied = await _print(client, opened, [quota - 1, quota, quota + 1], headers)
    assert denied.status_code == 403
    assert denied.json()["quota_remaining"] == 2
    second = await _print(client, opened, [quota - 1, quota], headers)
    assert second.status_code == 202
    assert second.json()["quota_remaining"] == 0
    assert (await _print(client, opened, [1], headers)).status_code == 403

    # A render that fails gives its pages back (the job is failed, the grant row untouched).
    async with admin_database.session(RlsContext.system()) as session:
        page = (
            await session.scalars(
                select(Page).where(Page.work_id == work.id, Page.seq == quota - 1)
            )
        ).one()
        page.derivative_key = None
        await session.flush()
    with pytest.raises(RuntimeError, match="no access derivative"):
        await _render(app, access_store, second.json()["public_id"])
    failed = await client.get(f"/reader/prints/{second.json()['public_id']}", headers=headers)
    assert failed.json()["state"] == "failed"
    assert failed.json()["quota_remaining"] == 2
    events = await _audit_actions(admin_database, "print.failed")
    assert len(events) == 1
    assert "no access derivative" in str(events[0].details["error"])


async def test_rdr_4_pages_outside_the_work_or_the_grant_are_refused(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, access_class=AccessClass.PAID, pages=10)
        holder = await make_user(session, "holder")
        grant = await make_grant(session, user=holder, work=work, page_from=3, page_to=6)
        grant.print_quota = 4
        await session.flush()
    headers = auth("holder", ["member"])
    opened = await _open(client, work.public_id, headers)
    for pages in ([2], [7], [3, 99], [1, 2, 3]):
        response = await _print(client, opened, pages, headers)
        assert response.status_code == 400, (pages, response.text)
        assert response.json()["code"] == "print_pages_invalid"
    assert (await _print(client, opened, [0], headers)).status_code == 422
    assert (await _print(client, opened, [], headers)).status_code == 422
    accepted = await _print(client, opened, [6, 3], headers)
    assert accepted.status_code == 202
    assert accepted.json()["pages"] == [3, 6]


async def test_rdr_4_anonymous_reader_of_an_open_work_cannot_print(
    client: httpx.AsyncClient, admin_database: Database
) -> None:
    """No grant, no quota, no print: the policy and the loader agree (ADR-0008)."""
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, access_class=AccessClass.OPEN, pages=4)
    opened = await _open(client, work.public_id)
    assert opened["grant"] is None
    response = await _print(client, opened, [1])
    assert response.status_code == 403
    assert response.json()["code"] == "grant_required"


async def test_print_requires_the_sessions_grant_token(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=4)
    headers = auth("maha", ["member"])
    opened = await _open(client, work.public_id, headers)
    no_token = await client.post(
        f"/reader/sessions/{opened['public_id']}/print", json={"pages": [1]}, headers=headers
    )
    assert no_token.status_code == 401
    assert no_token.json()["code"] == "grant_token_invalid"
    # The grant token alone is not enough either: print acts as the signed-in member.
    no_bearer = await _print(client, opened, [1])
    assert no_bearer.status_code == 403


async def test_print_job_is_visible_to_its_owner_and_rights_officers_only(
    client: httpx.AsyncClient, admin_database: Database, auth: Headers
) -> None:
    async with admin_database.session(RlsContext.system()) as session:
        work = await make_work(session, pages=4)
    owner = auth("maha", ["member"])
    opened = await _open(client, work.public_id, owner)
    job = (await _print(client, opened, [1], owner)).json()
    url = f"/reader/prints/{job['public_id']}"
    assert (await client.get(url, headers=owner)).status_code == 200
    assert (await client.get(url, headers=auth("other", ["member"]))).status_code == 403
    assert (await client.get(url, headers=auth("c", ["curator"], mfa=True))).status_code == 403
    officer = auth("r", ["rights_officer"], mfa=True)
    assert (await client.get(url, headers=officer)).status_code == 200
    assert (await client.post(f"{url}/link", headers=officer)).status_code == 403
    assert (await client.get(url)).status_code == 403
    assert (await client.get("/reader/prints/p8nothere1x")).status_code == 404


# --- The PDF writer ------------------------------------------------------------------------------


def test_pdf_writer_embeds_jpegs_at_the_declared_resolution() -> None:
    images = []
    for seq in (1, 2):
        image = _page_image(seq).resize(0.25)
        images.append(
            PdfImage(
                jpeg=bytes(image.jpegsave_buffer(Q=75)), width=image.width, height=image.height
            )
        )
    created = dt.datetime(2026, 10, 5, 12, 0, tzinfo=dt.UTC)
    pdf = build_pdf(
        images,
        ppi=150,
        title="أخبار بلدة سُمَيْرة",
        subject="w8abc · g8def · maha1234",
        producer="Jordanian Digital Heritage Platform",
        created_at=created,
    )
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 2
    assert reader.metadata is not None
    assert reader.metadata.title == "أخبار بلدة سُمَيْرة"
    assert reader.metadata.producer == "Jordanian Digital Heritage Platform"
    first = reader.pages[0]
    assert float(first.mediabox.width) == pytest.approx(images[0].width * 72 / 150)
    assert first["/Resources"]["/XObject"]["/Im0"].get_data() == images[0].jpeg
    assert first.extract_text() == ""
    # The PDF is not rendered back here on purpose: loading poppler into the test process
    # breaks Pillow's text layout for the seed renderer that runs later in the same session.
    with pytest.raises(ValueError, match="at least one page"):
        build_pdf([], ppi=150, title="t", subject="s", producer="p", created_at=created)


def test_validate_pages_sorts_dedupes_and_checks_the_grant_range() -> None:
    from jdhp_api.core.errors import PrintPagesError
    from jdhp_api.modules.access.models import Grant

    grant = Grant(page_from=None, page_to=None)
    assert printing.validate_pages([3, 1, 3], page_count=5, grant=grant) == [1, 3]
    ranged = Grant(page_from=2, page_to=4)
    assert printing.validate_pages([4, 2], page_count=5, grant=ranged) == [2, 4]
    for bad in ([0], [6], [1], [5]):
        with pytest.raises(PrintPagesError):
            printing.validate_pages(bad, page_count=5, grant=ranged)
