"""Seed the platform with the fictional book through the real pipeline.

``python -m jdhp_worker.seed [--scale 1.0] [--inline] [--no-publish]``

1. Render the seed book and upload masters and ground truth to the uploads bucket.
2. Register the intake batch through the API's intake service (as the seed curator).
3. Create the author, printer, vocabulary terms and the seed collection; publish the work.
4. Run the pipeline inline (``--inline``) or hand it to the workers through the broker.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from jdhp_api.core.auth import Principal, VerificationLevel
from jdhp_api.core.db import Database, RlsContext
from jdhp_api.core.orm import PublishState
from jdhp_api.modules.catalog import service as catalog
from jdhp_api.modules.catalog.models import Work
from jdhp_api.modules.ingest import service as ingest_service
from jdhp_api.modules.ingest.schemas import IntakeManifest
from jdhp_api.seed.generate import generate_isolated
from jdhp_api.seed.loader import load_book
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


def upload_seed(rt: Runtime, out: Path) -> dict[str, object]:
    settings = rt.settings
    for master in sorted((out / "master").glob("*.tif")):
        rt.store.put(
            settings.bucket_uploads,
            f"{STAGING_PREFIX}/{master.name}",
            master.read_bytes(),
            content_type="image/tiff",
        )
    for truth in sorted((out / "ground_truth").glob("*.json")):
        rt.store.put(
            settings.bucket_uploads,
            f"{STAGING_PREFIX}/ground_truth/{truth.name}",
            truth.read_bytes(),
            content_type="application/json",
        )
    manifest = json.loads((out / "manifest.json").read_text("utf-8"))
    manifest["staging_prefix"] = STAGING_PREFIX
    return manifest  # type: ignore[no-any-return]


async def register(
    database: Database, settings: WorkerSettings, manifest: dict[str, object], *, publish: bool
) -> tuple[str, str]:
    """Register the batch and catalog metadata as the seed curator.

    Returns the batch code and the work name.
    """
    book = load_book()
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
        collection = await catalog.create_collection(
            session,
            settings,
            kind=book.work.collection.kind,
            title_ar=book.work.collection.title_ar,
            title_en=book.work.collection.title_en,
            description_ar=book.work.collection.description_ar,
            description_en=book.work.collection.description_en,
            publish=publish,
        )
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


def seed(
    rt: Runtime, *, scale: float, inline: bool, publish: bool, out_dir: Path | None = None
) -> dict[str, object]:
    ensure_local_buckets(rt)
    with tempfile.TemporaryDirectory(prefix="jdhp-seed-") as tmp:
        out = out_dir or Path(tmp)
        generate_isolated(out, scale=scale)
        manifest = upload_seed(rt, out)
    # The seed registers as the app role: cataloguing is an application action, not a pipeline one.
    app_database = Database(rt.settings.sqlalchemy_url, pooled=False)
    try:
        batch_code, work_name = rt.run(
            register(app_database, rt.settings, manifest, publish=publish)
        )
    finally:
        rt.run(app_database.dispose())

    async def _batch_id() -> str:
        async with rt.database.session(RlsContext.system()) as session:
            batch = await ingest_service.get_batch_by_code(session, batch_code)
            assert batch is not None  # noqa: S101
            return str(batch.id)

    batch_id = rt.run(_batch_id())
    if inline:
        results = run_inline(rt, "jdhp.ingest.package", batch_id=batch_id)
        return {"batch": batch_code, "work": work_name, "tasks": len(results), "mode": "inline"}
    rt.send("jdhp.ingest.package", batch_id=batch_id)
    return {"batch": batch_code, "work": work_name, "mode": "queued"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--inline", action="store_true", help="run the pipeline in this process")
    parser.add_argument("--no-publish", action="store_true")
    args = parser.parse_args(argv)
    settings = get_worker_settings()
    rt = worker_runtime.build_runtime(settings, loop=not args.inline)
    result = seed(rt, scale=args.scale, inline=args.inline, publish=not args.no_publish)
    sys.stdout.write(json.dumps(result, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
