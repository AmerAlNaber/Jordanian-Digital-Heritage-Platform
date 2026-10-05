from __future__ import annotations

import uuid
from typing import Any

from jdhp_worker import runtime
from jdhp_worker.celery_app import app
from jdhp_worker.pipeline import derivatives


@app.task(name="jdhp.derivatives.generate", acks_late=True, max_retries=3, default_retry_delay=60)
def generate(page_id: str) -> dict[str, Any]:
    rt = runtime.current()
    return rt.run(derivatives.generate_for_page(rt, uuid.UUID(page_id)))
