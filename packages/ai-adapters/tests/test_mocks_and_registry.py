"""Adapters: interfaces honoured, mocks deterministic, registry records training terms (TRN-6)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jdhp_adapters import registry
from jdhp_adapters.base import (
    EmbeddingProvider,
    LanguageModelProvider,
    OcrProvider,
    Prompt,
    ProviderNotAvailableError,
)
from jdhp_adapters.mock.ocr import MockOcr, ground_truth_from_directory


async def test_mock_ocr_uses_ground_truth_when_present(tmp_path: Path) -> None:
    (tmp_path / "0007.json").write_text(
        json.dumps(
            {
                "width": 1890,
                "height": 2835,
                "lines": [
                    {
                        "text": "أخبار بلدة سُميرة",
                        "x": 100,
                        "y": 200,
                        "w": 1200,
                        "h": 60,
                        "confidence": 0.95,
                    },
                    {"text": "سطر ثانٍ", "x": 100, "y": 300, "w": 600, "h": 60, "confidence": 0.70},
                ],
            },
            ensure_ascii=False,
        ),
        "utf-8",
    )
    provider = MockOcr(ground_truth_from_directory(tmp_path))
    assert isinstance(provider, OcrProvider)
    result = await provider.recognize(b"image-bytes", page_ref="master/0007.tif")
    assert result.text == "أخبار بلدة سُميرة\nسطر ثانٍ"
    assert result.min_confidence == pytest.approx(0.70)
    assert 0.80 < result.average_confidence < 0.90
    assert result.page.width == 1890
    assert result.engine == "mock"


async def test_mock_ocr_placeholder_is_deterministic() -> None:
    provider = MockOcr()
    first = await provider.recognize(b"same", page_ref="p1")
    second = await provider.recognize(b"same", page_ref="p1")
    assert first.text == second.text
    assert first.text != (await provider.recognize(b"other", page_ref="p1")).text


async def test_mock_llm_and_embeddings_are_deterministic() -> None:
    llm = registry.make_language_model("mock")
    assert isinstance(llm, LanguageModelProvider)
    completion = await llm.complete(Prompt(system="translate", text="مرحبا", template_version="t1"))
    assert completion.text.startswith("[mock t1]")
    embedder = registry.make_embedding_provider("mock", dimensions=16)
    assert isinstance(embedder, EmbeddingProvider)
    result = await embedder.embed(["a", "b", "a"])
    assert result.dimensions == 16
    assert len(result.vectors) == 3
    assert result.vectors[0] == result.vectors[2]
    assert result.vectors[0] != result.vectors[1]
    assert sum(v * v for v in result.vectors[0]) == pytest.approx(1.0, abs=1e-5)


def test_trn_6_registry_records_training_terms() -> None:
    assert registry.provider_trains_on_inputs("ocr", "mock") is False
    assert registry.provider_trains_on_inputs("llm", "claude") is False
    assert registry.provider_trains_on_inputs("llm", "unknown") is None
    for kind, providers in registry.PROVIDERS.items():
        for name, info in providers.items():
            assert info.kind == kind
            assert info.name == name
            assert info.trains_on_inputs is False, (
                "no provider that trains on inputs may be registered"
            )


def test_unimplemented_providers_fail_loudly() -> None:
    with pytest.raises(ProviderNotAvailableError, match="Phase 1"):
        registry.make_ocr_provider("azure")
    with pytest.raises(ValueError, match="unknown"):
        registry.make_ocr_provider("tesseract")
