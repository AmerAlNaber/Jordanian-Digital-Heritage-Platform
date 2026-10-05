"""Search shapes: works and pages, regions on the scan, never text (SRCH-4, CAT-4)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from jdhp_api.modules.catalog.schemas import WorkSummary

Scope = Literal["catalog", "collection", "work"]


class Region(BaseModel):
    """A matched word box in page pixel coordinates (from ALTO)."""

    x: int
    y: int
    w: int
    h: int


class PageHit(BaseModel):
    seq: int
    ark: str
    label: str | None
    score: float
    scan_visible: bool = Field(
        description="Whether the caller may see this page's scan; regions are only given then"
    )
    thumbnail_available: bool
    regions: list[Region]


class WorkHit(BaseModel):
    work: WorkSummary
    score: float
    pages: list[PageHit]
    page_hits_total: int


class FacetBucket(BaseModel):
    value: str
    count: int


class SearchResponse(BaseModel):
    query: str
    scope: Scope
    expanded_terms: list[str]
    total_works: int
    total_page_hits: int
    works: list[WorkHit]
    facets: dict[str, list[FacetBucket]]
    limit: int
    offset: int
