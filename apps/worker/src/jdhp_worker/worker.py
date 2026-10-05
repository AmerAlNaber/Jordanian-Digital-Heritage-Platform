"""Entry point for the Celery processes: ``celery -A jdhp_worker.worker worker`` and ``beat``.

The shared application in :mod:`jdhp_worker.celery_app` is deliberately unconfigured at import so
tests can configure it for their own broker. The processes import this module instead, which
configures it from the environment first; a missing or invalid setting stops the process here,
before Celery would fall back to its defaults (SEC-19).
"""

from __future__ import annotations

from jdhp_worker.celery_app import app, configure
from jdhp_worker.settings import get_worker_settings

configure(get_worker_settings())

__all__ = ["app"]
