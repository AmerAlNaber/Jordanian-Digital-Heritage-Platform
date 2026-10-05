"""Offset pagination for lists. Keyset pagination replaces it where volumes demand (PRF-3)."""

from __future__ import annotations

from typing import Annotated

from fastapi import Query
from pydantic import BaseModel, ConfigDict

MAX_LIMIT = 100
MAX_OFFSET = 10_000


class PageParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = 20
    offset: int = 0


def page_params(
    limit: Annotated[int, Query(ge=1, le=MAX_LIMIT)] = 20,
    offset: Annotated[int, Query(ge=0, le=MAX_OFFSET)] = 0,
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


class Paginated[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int
