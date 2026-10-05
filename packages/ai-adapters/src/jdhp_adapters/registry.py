"""Provider registry: names, terms and factories. Configuration validation reads it (TRN-6).

Providers whose implementation arrives in a later phase are registered now so their terms are
on record and the configuration can refer to them; constructing one raises until it exists.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from jdhp_adapters.base import (
    EmbeddingProvider,
    LanguageModelProvider,
    OcrProvider,
    ProviderInfo,
    ProviderNotAvailableError,
)
from jdhp_adapters.mock import embeddings as mock_embeddings
from jdhp_adapters.mock import llm as mock_llm
from jdhp_adapters.mock import ocr as mock_ocr

PROVIDERS: dict[str, dict[str, ProviderInfo]] = {
    "ocr": {
        "mock": mock_ocr.INFO,
        "azure": ProviderInfo(
            name="azure",
            kind="ocr",
            display_name="Azure AI Document Intelligence",
            trains_on_inputs=False,
            self_hosted=False,
            data_region="configurable",
            available=False,
            note="Implementation lands in Phase 1 (ADR-0001 D5).",
        ),
        "kraken": ProviderInfo(
            name="kraken",
            kind="ocr",
            display_name="Kraken (self-hosted)",
            trains_on_inputs=False,
            self_hosted=True,
            data_region="local",
            available=False,
            note="Self-hosted option for historic scripts, Phase 3.",
        ),
    },
    "llm": {
        "mock": mock_llm.INFO,
        "claude": ProviderInfo(
            name="claude",
            kind="llm",
            display_name="Claude API",
            trains_on_inputs=False,
            self_hosted=False,
            data_region="configurable",
            available=False,
            note="First provider for translation, Phase 3 (ADR-0001 D6).",
        ),
    },
    "embedding": {
        "mock": mock_embeddings.INFO,
    },
}


def provider_info(kind: str, name: str) -> ProviderInfo | None:
    return PROVIDERS.get(kind, {}).get(name)


def provider_trains_on_inputs(kind: str, name: str) -> bool | None:
    """True, False, or None when the provider is unknown."""
    info = provider_info(kind, name)
    return None if info is None else info.trains_on_inputs


def _unavailable(info: ProviderInfo) -> Callable[..., Any]:
    def factory(**_config: Any) -> Any:
        msg = f"{info.display_name} is registered but not implemented yet. {info.note}"
        raise ProviderNotAvailableError(msg)

    return factory


def make_ocr_provider(name: str, **config: Any) -> OcrProvider:
    if name == "mock":
        return mock_ocr.MockOcr(config.get("ground_truth"))
    info = provider_info("ocr", name)
    if info is None:
        msg = f"unknown OCR provider {name!r}"
        raise ValueError(msg)
    return _unavailable(info)(**config)  # type: ignore[no-any-return]


def make_language_model(name: str, **config: Any) -> LanguageModelProvider:
    if name == "mock":
        return mock_llm.MockLanguageModel()
    info = provider_info("llm", name)
    if info is None:
        msg = f"unknown language model provider {name!r}"
        raise ValueError(msg)
    return _unavailable(info)(**config)  # type: ignore[no-any-return]


def make_embedding_provider(name: str, **config: Any) -> EmbeddingProvider:
    if name == "mock":
        return mock_embeddings.MockEmbeddings(int(config.get("dimensions", 1024)))
    info = provider_info("embedding", name)
    if info is None:
        msg = f"unknown embedding provider {name!r}"
        raise ValueError(msg)
    return _unavailable(info)(**config)  # type: ignore[no-any-return]
