"""Reader shapes: opening a session, the heartbeat, and the credentials the browser holds."""

from __future__ import annotations

import datetime as dt
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from jdhp_api.core.orm import PrintJobState, ReaderSessionState

FINGERPRINT_MIN = 8
FINGERPRINT_MAX = 512


class SessionOpen(BaseModel):
    model_config = ConfigDict(extra="forbid")

    work: str = Field(min_length=3, max_length=32, description="The work's public identifier")
    device_fingerprint: str = Field(min_length=FINGERPRINT_MIN, max_length=FINGERPRINT_MAX)


class Heartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_fingerprint: str = Field(min_length=FINGERPRINT_MIN, max_length=FINGERPRINT_MAX)
    pages_viewed: list[int] = Field(default_factory=list, max_length=100)
    dwell_seconds: int = Field(default=0, ge=0, le=3600)


class ReaderTokens(BaseModel):
    grant_token: str
    grant_token_expires_at: dt.datetime
    tile_token: str
    tile_token_expires_at: dt.datetime


class ReaderSessionOut(BaseModel):
    public_id: str
    work: str
    state: ReaderSessionState
    grant: str | None
    started_at: dt.datetime
    last_seen_at: dt.datetime
    idle_expires_at: dt.datetime
    hard_expires_at: dt.datetime
    heartbeat_interval_seconds: int
    manifest_url: str
    tiles_base_url: str
    tokens: ReaderTokens | None = None


class PrintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pages: list[Annotated[int, Field(ge=1, le=100_000)]] = Field(
        min_length=1, max_length=200, description="Sequence numbers of the pages to print"
    )


class PrintJobOut(BaseModel):
    public_id: str
    work: str
    grant: str
    state: PrintJobState
    pages: list[int]
    quota_remaining: int
    created_at: dt.datetime
    rendered_at: dt.datetime | None
    downloaded_at: dt.datetime | None


class PrintLinkOut(BaseModel):
    url: str = Field(description="Single-use download link, valid for fifteen minutes (SEC-15)")
    expires_at: dt.datetime
