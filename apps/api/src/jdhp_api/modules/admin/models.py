"""Administration: four-eyes approvals, break-glass access and field-level change history."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from jdhp_api.core.orm import (
    ApprovalKind,
    ApprovalState,
    Base,
    BreakGlassState,
    PrimaryKeyMixin,
    TimestampMixin,
    pg_enum,
)


class Approval(PrimaryKeyMixin, TimestampMixin, Base):
    """A proposal that needs a different person to approve it (SEC-9, ADM-3)."""

    __tablename__ = "approval"
    __table_args__ = (
        CheckConstraint("approved_by IS NULL OR approved_by <> proposed_by", name="two_people"),
    )

    kind: Mapped[ApprovalKind] = mapped_column(pg_enum(ApprovalKind, "approval_kind"))
    target_kind: Mapped[str] = mapped_column(String(32))
    target_id: Mapped[uuid.UUID]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    proposed_by: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"))
    state: Mapped[ApprovalState] = mapped_column(
        pg_enum(ApprovalState, "approval_state"), default=ApprovalState.PROPOSED, index=True
    )
    decided_at: Mapped[dt.datetime | None]
    reason: Mapped[str | None] = mapped_column(Text)


class BreakGlassRequest(PrimaryKeyMixin, TimestampMixin, Base):
    """Emergency access: a second admin approves, one hour, audited at high severity (SEC-8)."""

    __tablename__ = "break_glass_request"
    __table_args__ = (
        CheckConstraint("approver_id IS NULL OR approver_id <> requester_id", name="two_admins"),
    )

    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id"))
    approver_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"))
    scope: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    reason: Mapped[str] = mapped_column(Text)
    state: Mapped[BreakGlassState] = mapped_column(
        pg_enum(BreakGlassState, "break_glass_state"), default=BreakGlassState.REQUESTED
    )
    approved_at: Mapped[dt.datetime | None]
    expires_at: Mapped[dt.datetime | None]


class RecordChange(PrimaryKeyMixin, Base):
    """Field-level history for works and pages (ADM-2)."""

    __tablename__ = "record_change"

    entity_kind: Mapped[str] = mapped_column(String(32), index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(index=True)
    field: Mapped[str] = mapped_column(String(64))
    old_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    new_value: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"))
    changed_at: Mapped[dt.datetime]
    reason: Mapped[str | None] = mapped_column(Text)
