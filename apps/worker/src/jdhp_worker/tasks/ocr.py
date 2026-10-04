from __future__ import annotations

import uuid
from typing import Any

from jdhp_worker import runtime
from jdhp_worker.celery_app import app
from jdhp_worker.pipeline import ocr


@app.task(name="jdhp.ocr.recognize", acks_late=True, max_retries=5, default_retry_delay=120)
def recognize(page_id: str) -> dict[str, Any]:
    rt = runtime.current()
    return rt.run(ocr.recognize_page(rt, uuid.UUID(page_id)))
