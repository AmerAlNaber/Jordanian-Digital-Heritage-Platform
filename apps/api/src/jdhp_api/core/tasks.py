"""Dispatching background work to the Celery workers by task name.

The API never imports worker code; it sends named tasks over the broker (JSON only). Tests
use the recording dispatcher and assert on what would have been sent.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

from celery import Celery
from fastapi import Request

from jdhp_api.core.config import Settings, get_settings

QUEUE_BY_NAMESPACE = {
    "ingest": "ingest",
    "derivatives": "derivatives",
    "ocr": "ocr",
    "embeddings": "embeddings",
    "translation": "translation",
    "fixity": "fixity",
    "print": "derivatives",
    "mail": "mail",
    "maintenance": "maintenance",
}


def queue_for(task_name: str) -> str:
    parts = task_name.split(".")
    namespace = parts[1] if len(parts) > 2 and parts[0] == "jdhp" else parts[0]
    return QUEUE_BY_NAMESPACE.get(namespace, "default")


class TaskDispatcher(Protocol):
    def send(self, task_name: str, /, **kwargs: Any) -> str: ...


class CeleryDispatcher:
    def __init__(self, settings: Settings) -> None:
        self._app = Celery("jdhp-api-client", broker=str(settings.redis_url))
        self._app.conf.update(
            task_serializer="json",
            accept_content=["json"],
            result_serializer="json",
            task_ignore_result=True,
        )

    def send(self, task_name: str, /, **kwargs: Any) -> str:
        result = self._app.send_task(task_name, kwargs=kwargs, queue=queue_for(task_name))
        return str(result.id)


class RecordingDispatcher:
    """Collects dispatched tasks instead of sending them."""

    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []

    def send(self, task_name: str, /, **kwargs: Any) -> str:
        self.sent.append((task_name, kwargs))
        return str(uuid.uuid4())


def get_dispatcher(request: Request) -> TaskDispatcher:
    dispatcher = getattr(request.app.state, "dispatcher", None)
    if dispatcher is None:
        dispatcher = CeleryDispatcher(get_settings())
        request.app.state.dispatcher = dispatcher
    return dispatcher
