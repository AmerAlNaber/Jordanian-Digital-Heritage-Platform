"""Access shapes: a grant as its holder and the rights officer see it (ACS-2)."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field

from jdhp_api.core.orm import AccessClass, GrantSource


class GrantOut(BaseModel):
    public_id: str
    work: str
    work_access_class: AccessClass
    source: GrantSource
    starts_at: dt.datetime
    ends_at: dt.datetime
    device_limit: int
    page_from: int | None
    page_to: int | None
    print_quota: int
    print_used: int
    revoked: bool
    revoked_at: dt.datetime | None
    active: bool


class GrantRevoke(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=500)
