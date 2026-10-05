from __future__ import annotations

import uuid
from typing import Any

from jdhp_worker import runtime
from jdhp_worker.celery_app import app
from jdhp_worker.pipeline import printing


@app.task(name="jdhp.print.render", acks_late=True, max_retries=2, default_retry_delay=30)
def render(job_id: str) -> dict[str, Any]:
    rt = runtime.current()
    return rt.run(printing.render_job(rt, uuid.UUID(job_id)))
