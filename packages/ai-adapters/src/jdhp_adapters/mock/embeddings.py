"""Mock embeddings: deterministic unit vectors derived from the text, any dimension."""

from __future__ import annotations

import hashlib
import math
import struct
from collections.abc import Sequence

from jdhp_adapters.base import EmbeddingResult, ProviderInfo

INFO = ProviderInfo(
    name="mock",
    kind="embedding",
    display_name="Mock embeddings",
    trains_on_inputs=False,
    self_hosted=True,
    data_region="local",
    note="Development and test only.",
)


def _vector(text: str, dimensions: int) -> tuple[float, ...]:
    values: list[float] = []
    counter = 0
    seed = text.encode("utf-8")
    while len(values) < dimensions:
        block = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        values.extend(struct.unpack("<8f", block))
        counter += 1
    raw = [v if math.isfinite(v) else 0.0 for v in values[:dimensions]]
    norm = math.sqrt(sum(v * v for v in raw)) or 1.0
    return tuple(v / norm for v in raw)


class MockEmbeddings:
    info = INFO

    def __init__(self, dimensions: int = 1024) -> None:
        self.dimensions = dimensions

    async def embed(self, texts: Sequence[str]) -> EmbeddingResult:
        return EmbeddingResult(
            vectors=tuple(_vector(t, self.dimensions) for t in texts),
            model="mock-embeddings",
            model_version="1",
            dimensions=self.dimensions,
        )
