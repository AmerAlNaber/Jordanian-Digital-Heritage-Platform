from __future__ import annotations

import uuid
from typing import Any

from jdhp_worker import runtime
from jdhp_worker.celery_app import app
from jdhp_worker.pipeline import ingest


@app.task(name="jdhp.ingest.package", acks_late=True, max_retries=2, default_retry_delay=30)
def package(batch_id: str) -> dict[str, Any]:
    rt = runtime.current()
    return rt.run(ingest.package_batch(rt, uuid.UUID(batch_id)))
