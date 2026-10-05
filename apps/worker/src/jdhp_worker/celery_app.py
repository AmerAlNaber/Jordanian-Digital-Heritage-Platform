"""The Celery application. Configured from settings at startup, JSON only, acks late.

Processes start through :mod:`jdhp_worker.worker`, which configures this application from the
environment: ``celery -A jdhp_worker.worker worker -Q ingest,derivatives,ocr,...`` and
``celery -A jdhp_worker.worker beat``. Importing this module alone leaves the app unconfigured.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab

from jdhp_worker.settings import WorkerSettings

TASK_MODULES = (
    "jdhp_worker.tasks.ingest",
    "jdhp_worker.tasks.derivatives",
    "jdhp_worker.tasks.ocr",
    "jdhp_worker.tasks.embeddings",
    "jdhp_worker.tasks.fixity",
    "jdhp_worker.tasks.printing",
)

app = Celery("jdhp", include=list(TASK_MODULES))


def configure(settings: WorkerSettings, *, eager: bool = False) -> Celery:
    app.conf.update(
        broker_url=str(settings.redis_url),
        result_backend=str(settings.redis_url),
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_track_started=True,
        task_time_limit=1800,
        task_soft_time_limit=1500,
        result_expires=86400,
        timezone="UTC",
        enable_utc=True,
        broker_connection_retry_on_startup=True,
        task_default_queue="default",
        task_routes={
            "jdhp.ingest.*": {"queue": "ingest"},
            "jdhp.derivatives.*": {"queue": "derivatives"},
            "jdhp.ocr.*": {"queue": "ocr"},
            "jdhp.embeddings.*": {"queue": "embeddings"},
            "jdhp.translation.*": {"queue": "translation"},
            "jdhp.fixity.*": {"queue": "fixity"},
            "jdhp.print.*": {"queue": "derivatives"},
            "jdhp.mail.*": {"queue": "mail"},
            "jdhp.maintenance.*": {"queue": "maintenance"},
        },
        beat_schedule={
            # Quarterly fixity verification of every digital object (preservation rules).
            "fixity-sweep": {
                "task": "jdhp.fixity.sweep",
                "schedule": crontab(minute=0, hour=2, day_of_month=1, month_of_year="1,4,7,10"),
            },
        },
        task_always_eager=eager,
        task_eager_propagates=eager,
        task_store_eager_result=False,
    )
    return app


def main() -> None:  # pragma: no cover - process entry point
    from jdhp_worker.settings import get_worker_settings

    configure(get_worker_settings())
    app.start()


if __name__ == "__main__":  # pragma: no cover
    main()
