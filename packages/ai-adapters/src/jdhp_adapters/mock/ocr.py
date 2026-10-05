"""Mock OCR: returns ground truth when it exists for a page, a deterministic placeholder otherwise.

The seed book ships ground truth (line texts and boxes) so the whole pipeline runs for real
without an external service. Confidence values are deterministic per page so the under-85 percent
flag can be exercised on purpose.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from jdhp_adapters.base import OcrResult, ProviderInfo
from jdhp_metadata.alto import AltoPage, line_from_text, plain_text

INFO = ProviderInfo(
    name="mock",
    kind="ocr",
    display_name="Mock OCR (ground truth)",
    trains_on_inputs=False,
    self_hosted=True,
    data_region="local",
    note="Development and test only.",
)

GroundTruthLookup = Callable[[str], dict[str, Any] | None]


def ground_truth_from_directory(directory: Path) -> GroundTruthLookup:
    """Ground truth files ``<stem>.json`` hold width, height and lines (text, box, confidence)."""

    def lookup(page_ref: str) -> dict[str, Any] | None:
        ref = Path(page_ref)
        for candidate in (directory / f"{ref.stem}.json", directory / f"{ref.name}.json"):
            if candidate.exists():
                data = json.loads(candidate.read_text("utf-8"))
                return data if isinstance(data, dict) else None
        return None

    return lookup


def page_from_ground_truth(data: dict[str, Any], *, page_ref: str) -> AltoPage:
    lines = [
        line_from_text(
            str(item["text"]),
            x=int(item["x"]),
            y=int(item["y"]),
            w=int(item["w"]),
            h=int(item["h"]),
            confidence=float(item.get("confidence", 0.96)),
            rtl=bool(data.get("rtl", True)),
        )
        for item in data.get("lines", [])
    ]
    return AltoPage(
        width=int(data["width"]),
        height=int(data["height"]),
        lines=tuple(lines),
        language=str(data.get("language", "ara")),
        engine=INFO.name,
        engine_version="1",
        processed_at=dt.datetime.now(dt.UTC),
        page_id=Path(page_ref).name,
    )


def placeholder_page(image: bytes, *, page_ref: str) -> AltoPage:
    """No ground truth: one deterministic line so the pipeline still completes."""
    digest = hashlib.sha256(image).hexdigest()
    confidence = 0.80 + (int(digest[:2], 16) % 20) / 100
    line = line_from_text(
        f"نص تجريبي {digest[:8]}", x=100, y=100, w=800, h=50, confidence=confidence
    )
    return AltoPage(
        width=1000,
        height=1400,
        lines=(line,),
        engine=INFO.name,
        engine_version="1",
        processed_at=dt.datetime.now(dt.UTC),
        page_id=Path(page_ref).name,
    )


class MockOcr:
    info = INFO

    def __init__(self, ground_truth: GroundTruthLookup | None = None) -> None:
        self._lookup = ground_truth or (lambda _ref: None)

    async def recognize(
        self,
        image: bytes,
        *,
        page_ref: str,
        language_hints: Sequence[str] = (),  # noqa: ARG002 - the interface's parameter
    ) -> OcrResult:
        truth = self._lookup(page_ref)
        page = (
            page_from_ground_truth(truth, page_ref=page_ref)
            if truth
            else placeholder_page(image, page_ref=page_ref)
        )
        return OcrResult(
            page=page,
            text=plain_text(page),
            average_confidence=page.average_confidence(),
            min_confidence=page.min_confidence(),
            engine=page.engine,
            engine_version=page.engine_version,
        )
