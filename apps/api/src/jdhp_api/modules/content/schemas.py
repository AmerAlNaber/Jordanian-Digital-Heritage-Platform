"""Content object shapes. Every object says what it is and who or what produced it (SRC-1)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from jdhp_api.core.orm import Origin, ProvenanceType, ReviewStatus


class ContentObjectOut(BaseModel):
    public_id: str
    ark: str
    work_public_id: str
    page_seq: int | None
    provenance_type: ProvenanceType
    origin: Origin
    language: str
    script: str
    body: str | None
    segments: dict[str, Any] | None
    model: str | None
    model_version: str | None
    review_status: ReviewStatus
    reviewed_at: dt.datetime | None
    reviewer_subject: str | None
    generated_at: dt.datetime | None
    created_at: dt.datetime
    label_ar: str
    label_en: str


class ContentObjectCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provenance_type: ProvenanceType
    origin: Origin
    language: str = Field(min_length=3, max_length=3)
    script: str = Field(min_length=4, max_length=4)
    body: str = Field(min_length=1, max_length=200_000)
    page_seq: int | None = Field(default=None, ge=1)
    segments: dict[str, Any] | None = None
    model: str | None = Field(default=None, max_length=128)
    model_version: str | None = Field(default=None, max_length=64)
    prompt_template_version: str | None = Field(default=None, max_length=64)
    glossary_version: str | None = Field(default=None, max_length=64)
    self_assessment: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def _ai_needs_model(self) -> ContentObjectCreate:
        if self.provenance_type in {ProvenanceType.SCAN, ProvenanceType.OCR}:
            msg = "scan and ocr are page facts, not content objects"
            raise ValueError(msg)
        if self.origin == Origin.AI and not (self.model and self.model_version):
            msg = "ai objects must record model and model_version"
            raise ValueError(msg)
        return self
