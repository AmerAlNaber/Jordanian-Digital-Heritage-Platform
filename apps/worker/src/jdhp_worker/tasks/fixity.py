from __future__ import annotations

import uuid
from typing import Any

from jdhp_worker import runtime
from jdhp_worker.celery_app import app
from jdhp_worker.pipeline import fixity


@app.task(name="jdhp.fixity.verify", acks_late=True, max_retries=2, default_retry_delay=300)
def verify(digital_object_id: str) -> dict[str, Any]:
    rt = runtime.current()
    return rt.run(fixity.verify_digital_object(rt, uuid.UUID(digital_object_id)))


@app.task(name="jdhp.fixity.sweep", acks_late=True)
def sweep() -> dict[str, Any]:
    rt = runtime.current()
    return rt.run(fixity.sweep(rt))
