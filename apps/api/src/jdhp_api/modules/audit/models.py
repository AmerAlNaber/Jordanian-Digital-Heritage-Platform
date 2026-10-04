"""The audit log: append-only, hash-chained, shipped daily to write-once storage (SEC-25)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import BigInteger, Identity, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from jdhp_api.core.ids import uuid7
from jdhp_api.core.orm import AuditOutcome, AuditSeverity, Base, pg_enum

GENESIS_HASH = "0" * 64


class AuditEvent(Base):
    __tablename__ = "audit_event"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    seq: Mapped[int] = mapped_column(BigInteger, Identity(always=True), unique=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(index=True)
    actor_id: Mapped[str] = mapped_column(String(64), index=True)
    actor_type: Mapped[str] = mapped_column(String(16))
    actor_roles: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    action: Mapped[str] = mapped_column(String(64), index=True)
    resource_kind: Mapped[str] = mapped_column(String(32), index=True)
    resource_id: Mapped[str] = mapped_column(String(128), index=True)
    outcome: Mapped[AuditOutcome] = mapped_column(pg_enum(AuditOutcome, "audit_outcome"))
    severity: Mapped[AuditSeverity] = mapped_column(pg_enum(AuditSeverity, "audit_severity"))
    ip: Mapped[str | None] = mapped_column(String(45))
    user_agent: Mapped[str | None] = mapped_column(Text)
    request_id: Mapped[str | None] = mapped_column(String(36), index=True)
    details: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    prev_hash: Mapped[str] = mapped_column(String(64))
    hash: Mapped[str] = mapped_column(String(64), unique=True)
