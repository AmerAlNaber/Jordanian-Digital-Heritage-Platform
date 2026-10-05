"""Run the pipeline in-process: the seed command and tests dispatch follow-up tasks to a queue."""

from __future__ import annotations

import uuid
from collections import deque
from collections.abc import Callable, Coroutine
from typing import Any

from jdhp_worker.pipeline import derivatives, embeddings, fixity, ingest, ocr, printing
from jdhp_worker.runtime import Runtime

PipelineFn = Callable[..., Coroutine[Any, Any, dict[str, object]]]

HANDLERS: dict[str, Callable[[Runtime, dict[str, Any]], Coroutine[Any, Any, dict[str, object]]]] = {
    "jdhp.ingest.package": lambda rt, kw: ingest.package_batch(rt, uuid.UUID(kw["batch_id"])),
    "jdhp.derivatives.generate": lambda rt, kw: derivatives.generate_for_page(
        rt, uuid.UUID(kw["page_id"])
    ),
    "jdhp.ocr.recognize": lambda rt, kw: ocr.recognize_page(rt, uuid.UUID(kw["page_id"])),
    "jdhp.embeddings.compute": lambda rt, kw: embeddings.compute_for_page(
        rt, uuid.UUID(kw["page_id"])
    ),
    "jdhp.fixity.verify": lambda rt, kw: fixity.verify_digital_object(
        rt, uuid.UUID(kw["digital_object_id"])
    ),
    "jdhp.print.render": lambda rt, kw: printing.render_job(rt, uuid.UUID(kw["job_id"])),
}


def run_inline(rt: Runtime, task_name: str, **kwargs: Any) -> list[dict[str, object]]:
    """Execute a task and everything it enqueues, breadth first, on the current thread."""
    queue: deque[tuple[str, dict[str, Any]]] = deque([(task_name, kwargs)])
    previous = rt.enqueue
    rt.enqueue = lambda name, kw: queue.append((name, kw))
    results: list[dict[str, object]] = []
    try:
        while queue:
            name, kw = queue.popleft()
            handler = HANDLERS.get(name)
            if handler is None:
                msg = f"no inline handler for {name}"
                raise KeyError(msg)
            results.append(rt.run(handler(rt, kw)))
    finally:
        rt.enqueue = previous
    return results
