"""Digitization intake manifest (ADM-1). Validated at the edge; checksums verified by the worker."""

from __future__ import annotations

import datetime as dt
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from jdhp_api.core.orm import IntakeState, PageType
from jdhp_api.modules.catalog.schemas import WorkCreate

SHA256 = re.compile(r"^[0-9a-f]{64}$")
SAFE_FILENAME = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


class ManifestPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=1)
    filename: str
    sha256: str
    label: str | None = Field(default=None, max_length=64)
    page_type: PageType = PageType.TEXT
    language: str | None = Field(default=None, min_length=3, max_length=3)
    script: str | None = Field(default=None, min_length=4, max_length=4)
    section_title: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=2000)

    @field_validator("filename")
    @classmethod
    def _safe_filename(cls, value: str) -> str:
        if not SAFE_FILENAME.match(value) or ".." in value:
            msg = "filename may contain letters, digits, dot, underscore and hyphen only"
            raise ValueError(msg)
        return value

    @field_validator("sha256")
    @classmethod
    def _sha(cls, value: str) -> str:
        if not SHA256.match(value):
            msg = "sha256 must be 64 lowercase hex characters"
            raise ValueError(msg)
        return value


class Capture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device: str = Field(max_length=200)
    captured_on: dt.date
    color_target_ref: str | None = Field(default=None, max_length=200)
    operator: str | None = Field(default=None, max_length=200)


class ItemInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shelfmark: str | None = Field(default=None, max_length=200)
    condition: str | None = Field(default=None, max_length=2000)
    provenance: str | None = Field(default=None, max_length=5000)


class IntakeManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work_public_id: str | None = None
    new_work: WorkCreate | None = None
    item: ItemInfo = Field(default_factory=ItemInfo)
    capture: Capture
    staging_prefix: str = Field(max_length=200)
    pages: list[ManifestPage] = Field(min_length=1, max_length=2000)

    @field_validator("staging_prefix")
    @classmethod
    def _prefix(cls, value: str) -> str:
        if not re.match(r"^[A-Za-z0-9/_-]+$", value) or ".." in value or value.startswith("/"):
            msg = "staging_prefix must be a relative key prefix"
            raise ValueError(msg)
        return value.rstrip("/")

    @model_validator(mode="after")
    def _one_work_reference(self) -> IntakeManifest:
        if (self.work_public_id is None) == (self.new_work is None):
            msg = "give exactly one of work_public_id or new_work"
            raise ValueError(msg)
        seqs = [p.seq for p in self.pages]
        if sorted(seqs) != list(range(1, len(seqs) + 1)):
            msg = "page sequence numbers must be 1..n without gaps"
            raise ValueError(msg)
        if len({p.filename for p in self.pages}) != len(self.pages):
            msg = "page filenames must be unique"
            raise ValueError(msg)
        return self


class IntakeBatchOut(BaseModel):
    code: str
    state: IntakeState
    work_public_id: str
    page_count: int
    error_detail: str | None
    created_at: dt.datetime
    completed_at: dt.datetime | None
