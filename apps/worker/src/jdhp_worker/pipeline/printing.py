"""Print rendering: the worker side of RDR-4. The logic lives with the reader module."""

from __future__ import annotations

import uuid

from jdhp_api.core.tokens import ForensicKeys
from jdhp_api.modules.reader import printing
from jdhp_worker.runtime import Runtime


async def render_job(rt: Runtime, job_id: uuid.UUID) -> dict[str, object]:
    return await printing.render_print(
        database=rt.database,
        store=rt.store,
        settings=rt.settings,
        forensic_keys=ForensicKeys(rt.settings),
        job_id=job_id,
    )
