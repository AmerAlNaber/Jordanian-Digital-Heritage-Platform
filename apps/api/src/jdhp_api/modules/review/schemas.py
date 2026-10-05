"""Review portal shapes (ADM-8, REV-2)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from jdhp_api.core.orm import ReviewStatus
from jdhp_api.modules.content.schemas import ContentObjectOut


class ReviewTaskOut(BaseModel):
    content_public_id: str
    work_public_id: str
    state: ReviewStatus
    assignee_subject: str | None
    due_at: dt.datetime | None
    priority: int
    attempt: int
    reviewer_note: str | None
    decided_at: dt.datetime | None
    created_at: dt.datetime
    content: ContentObjectOut
    page_seq: int | None
    ocr_text: str | None


class ApproveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    edited_body: str | None = Field(default=None, max_length=200_000)
    note: str | None = Field(default=None, max_length=5000)


class RejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=5000)
