"""Adapter interfaces. Every provider declares whether it trains on inputs (TRN-6)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from jdhp_metadata.alto import AltoPage


@dataclass(frozen=True, slots=True)
class ProviderInfo:
    name: str
    kind: str  # ocr | llm | embedding
    display_name: str
    trains_on_inputs: bool
    self_hosted: bool
    data_region: str
    available: bool = True
    note: str = ""


@dataclass(frozen=True, slots=True)
class OcrResult:
    page: AltoPage
    text: str
    average_confidence: float
    min_confidence: float
    engine: str
    engine_version: str


@dataclass(frozen=True, slots=True)
class Prompt:
    """What a language model receives: instructions, the source text and bounded context."""

    system: str
    text: str
    context: dict[str, str] = field(default_factory=dict)
    template_version: str = "0"
    max_tokens: int = 2048


@dataclass(frozen=True, slots=True)
class Completion:
    text: str
    model: str
    model_version: str
    input_tokens: int
    output_tokens: int


@dataclass(frozen=True, slots=True)
class EmbeddingResult:
    vectors: tuple[tuple[float, ...], ...]
    model: str
    model_version: str
    dimensions: int


@runtime_checkable
class OcrProvider(Protocol):
    info: ProviderInfo

    async def recognize(
        self, image: bytes, *, page_ref: str, language_hints: Sequence[str] = ()
    ) -> OcrResult: ...


@runtime_checkable
class LanguageModelProvider(Protocol):
    info: ProviderInfo

    async def complete(self, prompt: Prompt) -> Completion: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    info: ProviderInfo

    async def embed(self, texts: Sequence[str]) -> EmbeddingResult: ...


class ProviderNotAvailableError(RuntimeError):
    """The provider is registered but its implementation arrives in a later phase."""
