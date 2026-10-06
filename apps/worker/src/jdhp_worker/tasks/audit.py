from __future__ import annotations

import datetime as dt
from typing import Any

from jdhp_worker import runtime
from jdhp_worker.celery_app import app
from jdhp_worker.pipeline import audit_archive


@app.task(name="jdhp.audit.ship", acks_late=True, max_retries=3, default_retry_delay=600)
def ship(day: str | None = None) -> dict[str, Any]:
    """Ship one day's audit events to the write-once archive; yesterday when no day is given."""
    rt = runtime.current()
    if day is None:
        return rt.run(audit_archive.ship_previous_day(rt))
    return rt.run(audit_archive.ship_day(rt, dt.date.fromisoformat(day)))
