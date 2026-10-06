"""Typed access to the seed book definition."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

BlockKind = Literal["display", "center", "heading", "body", "figure", "caption", "table", "stamp"]


class SeedBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: BlockKind
    lines: list[str] = Field(default_factory=list)
    columns: list[str] | None = None
    rows: list[list[str]] | None = None


class SeedPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seq: int = Field(ge=1)
    type: str
    label: str | None
    section: str | None = None
    blocks: list[SeedBlock]

    @property
    def filename(self) -> str:
        return f"{self.seq:04d}.tif"

    def text_lines(self) -> list[str]:
        """Every line of text on the page in reading order, table cells included."""
        lines: list[str] = []
        for block in self.blocks:
            if block.kind == "table" and block.columns is not None and block.rows is not None:
                lines.append(" | ".join(block.columns))
                lines.extend(" | ".join(row) for row in block.rows)
            else:
                lines.extend(block.lines)
        return lines


class SeedAgent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    kind: str
    name_ar: str
    name_latin: str | None
    dates_edtf: str | None


class SeedTerm(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scheme: str
    facet: str
    code: str
    label_ar: str
    label_en: str | None


class SeedCollection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    title_ar: str
    title_en: str | None
    description_ar: str | None
    description_en: str | None


class SeedWork(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title_ar: str
    title_translit: str | None
    title_en: str | None
    uniform_title: str | None
    language: str
    script: str
    date_edtf: str | None
    date_hijri: str | None
    extent: str | None
    description_ar: str | None
    description_en: str | None
    rights_statement: str
    rights_basis: str | None
    access_class: str
    agents: list[SeedAgent]
    terms: list[SeedTerm]
    collection: SeedCollection

    def work_create_fields(self) -> dict[str, Any]:
        """The subset accepted by the intake manifest's ``new_work``."""
        return self.model_dump(exclude={"agents", "terms", "collection"})


class SeedItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shelfmark: str | None
    condition: str | None
    provenance: str | None


class SeedCapture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device: str
    color_target_ref: str | None
    operator: str | None


class SeedBook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fictional_notice: str
    work: SeedWork
    item: SeedItem
    capture: SeedCapture
    pages: list[SeedPage]


MAIN_SLUG = "seed-book"


@cache
def load_book() -> SeedBook:
    """The 40-page seed book, the reference work of every test."""
    text = resources.files("jdhp_api.seed.book").joinpath("book.json").read_text("utf-8")
    return SeedBook.model_validate(json.loads(text))


@cache
def load_library() -> tuple[tuple[str, SeedBook], ...]:
    """The short books of the fictional library, in file order, each named by its file stem."""
    folder = resources.files("jdhp_api.seed.library")
    entries = sorted(
        (e for e in folder.iterdir() if e.name.endswith(".json")), key=lambda e: e.name
    )
    return tuple(
        (entry.name[:-5], SeedBook.model_validate(json.loads(entry.read_text("utf-8"))))
        for entry in entries
    )


def load_all() -> tuple[tuple[str, SeedBook], ...]:
    """Every seed book: the reference work first, then the library."""
    return ((MAIN_SLUG, load_book()), *load_library())


def find_book(slug: str) -> SeedBook:
    for name, book in load_all():
        if name == slug:
            return book
    msg = f"no seed book named {slug!r}"
    raise KeyError(msg)
