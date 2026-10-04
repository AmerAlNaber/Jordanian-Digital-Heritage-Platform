"""Catalog response and request shapes. Public identifiers only; never internal ids (CAT-1)."""

from __future__ import annotations

import datetime as dt
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from jdhp_api.core.orm import (
    AccessClass,
    AgentRole,
    CollectionKind,
    PageType,
    PublishState,
    TermFacet,
)


class Citation(BaseModel):
    ark: str
    ar: str
    en: str


class AgentRef(BaseModel):
    public_id: str
    ark: str
    name_ar: str
    name_latin: str | None
    role: AgentRole


class TermRef(BaseModel):
    scheme: str
    facet: TermFacet
    code: str
    label_ar: str
    label_en: str | None


class CollectionRef(BaseModel):
    public_id: str
    ark: str
    title_ar: str
    title_en: str | None


class WorkSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    public_id: str
    ark: str
    title_ar: str
    title_translit: str | None
    title_en: str | None
    language: str
    script: str
    date_edtf: str | None
    date_hijri: str | None
    access_class: AccessClass
    publish_state: PublishState
    page_count: int
    sample_page_limit: int | None
    thumbnail_available: bool


class WorkDetail(WorkSummary):
    uniform_title: str | None
    description_ar: str | None
    description_en: str | None
    extent: str | None
    rights_statement: str
    rights_basis: str | None = None
    pricing: dict[str, Any] | None = None
    published_at: dt.datetime | None
    agents: list[AgentRef]
    terms: list[TermRef]
    collections: list[CollectionRef]
    provenance: str | None
    citation: Citation
    can_read: bool
    can_request_access: bool


class WorkCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_ar: str = Field(min_length=1, max_length=1000)
    title_translit: str | None = Field(default=None, max_length=1000)
    title_en: str | None = Field(default=None, max_length=1000)
    uniform_title: str | None = Field(default=None, max_length=1000)
    language: str = Field(default="ara", min_length=3, max_length=3)
    script: str = Field(default="Arab", min_length=4, max_length=4)
    date_edtf: str | None = Field(default=None, max_length=64)
    date_hijri: str | None = Field(default=None, max_length=64)
    description_ar: str | None = Field(default=None, max_length=20_000)
    description_en: str | None = Field(default=None, max_length=20_000)
    extent: str | None = Field(default=None, max_length=200)
    rights_statement: str | None = Field(default=None, max_length=500)
    rights_basis: str | None = Field(default=None, max_length=2000)
    access_class: AccessClass = AccessClass.REGISTERED


class WorkUpdate(BaseModel):
    """Partial update. Access class and pricing are not here: they need a second approver."""

    model_config = ConfigDict(extra="forbid")

    title_ar: str | None = Field(default=None, min_length=1, max_length=1000)
    title_translit: str | None = Field(default=None, max_length=1000)
    title_en: str | None = Field(default=None, max_length=1000)
    uniform_title: str | None = Field(default=None, max_length=1000)
    language: str | None = Field(default=None, min_length=3, max_length=3)
    script: str | None = Field(default=None, min_length=4, max_length=4)
    date_edtf: str | None = Field(default=None, max_length=64)
    date_hijri: str | None = Field(default=None, max_length=64)
    description_ar: str | None = Field(default=None, max_length=20_000)
    description_en: str | None = Field(default=None, max_length=20_000)
    extent: str | None = Field(default=None, max_length=200)
    rights_statement: str | None = Field(default=None, max_length=500)
    rights_basis: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=1000)


class PageSummary(BaseModel):
    seq: int
    ark: str
    label: str | None
    page_type: PageType
    width_px: int | None
    height_px: int | None
    in_sample_range: bool
    thumbnail_available: bool
    section_title: str | None
    description: str | None


class CollectionSummary(BaseModel):
    public_id: str
    ark: str
    kind: CollectionKind
    title_ar: str
    title_en: str | None
    description_ar: str | None
    description_en: str | None
    work_count: int


class CollectionDetail(CollectionSummary):
    works: list[WorkSummary]


class TermSummary(BaseModel):
    scheme: str
    facet: TermFacet
    code: str
    label_ar: str
    label_en: str | None
    landing_ar: str | None
    landing_en: str | None
    latitude: float | None
    longitude: float | None
    work_count: int


class Resolution(BaseModel):
    kind: str
    public_id: str
    ark: str
    path: str
