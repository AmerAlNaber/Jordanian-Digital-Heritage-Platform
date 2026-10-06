"""Seed the platform with the fictional library through the real pipeline.

``python -m jdhp_worker.seed [--scale 1.0] [--inline] [--no-publish] [--only SLUG ...]``

For the 40-page seed book and each short book of the library (ADR-0001 D15):

1. Render the book and upload masters and ground truth to the uploads bucket.
2. Register the intake batch through the API's intake service (as the seed curator).
3. Create the agents and vocabulary terms, attach the collection (shared across books) and
   publish the work; an embargoed work is published too, so staff-only visibility is exercised.
4. Run the pipeline inline (``--inline``) or hand each batch to the workers through the broker.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from sqlalchemy import select

from jdhp_api.core.auth import Principal, VerificationLevel
from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.orm import PublishState
from jdhp_api.modules.catalog import service as catalog
from jdhp_api.modules.catalog.models import Collection, Work
from jdhp_api.modules.ingest import service as ingest_service
from jdhp_api.modules.ingest.schemas import IntakeManifest
from jdhp_api.seed.generate import generate_isolated, staging_prefix_for
from jdhp_api.seed.loader import MAIN_SLUG, SeedBook, load_all, load_book
from jdhp_worker import runtime as worker_runtime
from jdhp_worker.inline import run_inline
from jdhp_worker.runtime import Runtime
from jdhp_worker.settings import WorkerSettings, get_worker_settings

STAGING_PREFIX = "intake/seed-book"
SEED_PRINCIPAL = Principal(
    id="seed",
    roles=frozenset({"curator"}),
    authenticated=True,
    verification_level=VerificationLevel.PHONE,
    mfa=True,
)


def ensure_local_buckets(rt: Runtime) -> None:
    settings = rt.settings
    if settings.env.is_deployed:
        return
    rt.ingest_store.ensure_bucket(settings.bucket_preservation, object_lock=True)
    for bucket in (settings.bucket_access, settings.bucket_uploads, settings.bucket_exports):
        rt.store.ensure_bucket(bucket)
    rt.store.ensure_bucket(settings.bucket_audit_archive, object_lock=True)


def upload_seed(rt: Runtime, out: Path, prefix: str = STAGING_PREFIX) -> dict[str, object]:
    """Upload one rendered book's masters and ground truth under ``prefix``; return its manifest."""
    settings = rt.settings
    for master in sorted((out / "master").glob("*.tif")):
        rt.store.put(
            settings.bucket_uploads,
            f"{prefix}/{master.name}",
            master.read_bytes(),
            content_type="image/tiff",
        )
    for truth in sorted((out / "ground_truth").glob("*.json")):
        rt.store.put(
            settings.bucket_uploads,
            f"{prefix}/ground_truth/{truth.name}",
            truth.read_bytes(),
            content_type="application/json",
        )
    manifest = json.loads((out / "manifest.json").read_text("utf-8"))
    manifest["staging_prefix"] = prefix
    return manifest  # type: ignore[no-any-return]


async def _collection_for(
    session: Any, settings: WorkerSettings, book: SeedBook, *, publish: bool
) -> Collection:
    """The book's collection, created once and shared by every book that names it."""
    wanted = book.work.collection
    stmt = select(Collection).where(
        Collection.kind == wanted.kind, Collection.title_ar == wanted.title_ar
    )
    existing = (await session.scalars(stmt)).first()
    if existing is not None:
        return existing  # type: ignore[no-any-return]
    return await catalog.create_collection(
        session,
        settings,
        kind=wanted.kind,
        title_ar=wanted.title_ar,
        title_en=wanted.title_en,
        description_ar=wanted.description_ar,
        description_en=wanted.description_en,
        publish=publish,
    )


async def register(
    database: Database,
    settings: WorkerSettings,
    manifest: dict[str, object],
    *,
    publish: bool,
    book: SeedBook | None = None,
) -> tuple[str, str]:
    """Register one book's batch and catalog metadata as the seed curator.

    Returns the batch code and the work name.
    """
    book = book or load_book()
    async with database.session(SEED_PRINCIPAL.rls_context()) as session:
        batch = await ingest_service.register_batch(
            session,
            IntakeManifest.model_validate(manifest),
            SEED_PRINCIPAL,
            settings,
            request_id="seed",
        )
        work = await session.get(Work, batch.work_id)
        assert work is not None  # noqa: S101 - register_batch always creates or finds the work
        for ordinal, seed_agent in enumerate(book.work.agents):
            agent = await catalog.create_agent(
                session,
                settings,
                kind=seed_agent.kind,
                name_ar=seed_agent.name_ar,
                name_latin=seed_agent.name_latin,
                dates_edtf=seed_agent.dates_edtf,
            )
            await catalog.link_agent(session, work, agent, seed_agent.role, ordinal)
        for seed_term in book.work.terms:
            term = await catalog.upsert_term(
                session,
                scheme=seed_term.scheme,
                facet=seed_term.facet,
                code=seed_term.code,
                label_ar=seed_term.label_ar,
                label_en=seed_term.label_en,
            )
            await catalog.link_term(session, work, term)
        collection = await _collection_for(session, settings, book, publish=publish)
        await catalog.add_to_collection(session, collection, work)
        if publish:
            await catalog.set_publish_state(
                session,
                work,
                PublishState.PUBLISHED,
                actor_id="seed",
                actor_roles=("curator",),
                request_id="seed",
            )
        return batch.code, work.public_id


def seed_one(
    rt: Runtime,
    app_database: Database,
    slug: str,
    book: SeedBook,
    *,
    scale: float,
    inline: bool,
    publish: bool,
    out_dir: Path | None = None,
) -> dict[str, object]:
    """Render, upload, register and ingest one book."""
    with tempfile.TemporaryDirectory(prefix=f"jdhp-seed-{slug}-") as tmp:
        out = out_dir or Path(tmp)
        generate_isolated(out, scale=scale, book=slug)
        manifest = upload_seed(rt, out, prefix=staging_prefix_for(slug))
    batch_code, work_name = rt.run(
        register(app_database, rt.settings, manifest, publish=publish, book=book)
    )

    async def _batch_id() -> str:
        async with rt.database.session(RlsContext.system()) as session:
            batch = await ingest_service.get_batch_by_code(session, batch_code)
            assert batch is not None  # noqa: S101
            return str(batch.id)

    batch_id = rt.run(_batch_id())
    summary: dict[str, object] = {
        "book": slug,
        "batch": batch_code,
        "work": work_name,
        "access_class": book.work.access_class,
        "pages": len(book.pages),
    }
    if inline:
        results = run_inline(rt, "jdhp.ingest.package", batch_id=batch_id)
        summary["tasks"] = len(results)
    else:
        rt.send("jdhp.ingest.package", batch_id=batch_id)
    return summary


def seed(
    rt: Runtime,
    *,
    scale: float,
    inline: bool,
    publish: bool,
    out_dir: Path | None = None,
    only: Sequence[str] = (),
) -> dict[str, object]:
    """Seed every book (or the ``only`` slugs); the 40-page seed book always goes first."""
    ensure_local_buckets(rt)
    chosen = [(slug, book) for slug, book in load_all() if not only or slug in only]
    if only and len(chosen) != len(set(only)):
        unknown = sorted(set(only) - {slug for slug, _ in chosen})
        msg = f"unknown seed books: {', '.join(unknown)}"
        raise SystemExit(msg)
    # The seed registers as the app role: cataloguing is an application action, not a pipeline one.
    app_database = Database(rt.settings.sqlalchemy_url, pooled=False)
    books: list[dict[str, object]] = []
    try:
        for slug, book in chosen:
            books.append(
                seed_one(
                    rt,
                    app_database,
                    slug,
                    book,
                    scale=scale,
                    inline=inline,
                    publish=publish,
                    out_dir=(out_dir / slug) if out_dir else None,
                )
            )
    finally:
        rt.run(app_database.dispose())
    return {"books": books, "mode": "inline" if inline else "queued"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--inline", action="store_true", help="run the pipeline in this process")
    parser.add_argument("--no-publish", action="store_true")
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        metavar="SLUG",
        help=f"seed only this book (repeatable); the 40-page book is {MAIN_SLUG!r}",
    )
    args = parser.parse_args(argv)
    settings = get_worker_settings()
    rt = worker_runtime.build_runtime(settings, loop=not args.inline)
    result = seed(
        rt, scale=args.scale, inline=args.inline, publish=not args.no_publish, only=args.only
    )
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
