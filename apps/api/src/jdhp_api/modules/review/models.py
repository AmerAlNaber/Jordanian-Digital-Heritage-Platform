"""Review queue: one task per AI-generated object until a Reviewer decides (ADM-8, REV-3)."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from jdhp_api.core.orm import Base, PrimaryKeyMixin, ReviewStatus, TimestampMixin, pg_enum


class ReviewTask(PrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "review_task"

    content_object_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("content_object.id"), index=True
    )
    work_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("work.id"), index=True)
    state: Mapped[ReviewStatus] = mapped_column(
        pg_enum(ReviewStatus, "review_status"), default=ReviewStatus.PENDING, index=True
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"), index=True)
    due_at: Mapped[dt.datetime | None]
    priority: Mapped[int] = mapped_column(Integer, default=0)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    edit_diff: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("user.id"))
    decided_at: Mapped[dt.datetime | None]
