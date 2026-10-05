"""Audit viewer shapes (ADM-5)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel

from jdhp_api.core.orm import AuditOutcome, AuditSeverity


class AuditEventOut(BaseModel):
    seq: int
    occurred_at: dt.datetime
    actor_id: str
    actor_type: str
    actor_roles: list[str]
    action: str
    resource_kind: str
    resource_id: str
    outcome: AuditOutcome
    severity: AuditSeverity
    ip: str | None
    request_id: str | None
    details: dict[str, Any]
    hash: str


class ChainVerification(BaseModel):
    intact: bool
    events_checked: int
