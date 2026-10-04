"""Unit tests for validation, chunking, derivatives and the watermark."""

from __future__ import annotations

import hashlib
import io
from typing import Any

import pytest
from PIL import Image, ImageCms

from jdhp_worker.pipeline.derivatives import access_derivative, webp_resized
from jdhp_worker.pipeline.embeddings import chunk_text
from jdhp_worker.pipeline.validation import MasterValidationError, validate_master
from jdhp_worker.pipeline.watermark import platform_mark


def tiff_bytes(
    *, mode: str = "RGB", dpi: int = 400, icc: bool = True, size: tuple[int, int] = (64, 96)
) -> bytes:
    image = Image.new(mode, size, (200, 190, 170) if mode == "RGB" else 200)
    out = io.BytesIO()
    kwargs: dict[str, Any] = {"dpi": (dpi, dpi), "compression": None}
    if icc:
        kwargs["icc_profile"] = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    image.save(out, format="TIFF", **kwargs)
    return out.getvalue()


def test_valid_master_passes() -> None:
    data = tiff_bytes()
    info = validate_master(
        data, expected_sha256=hashlib.sha256(data).hexdigest(), min_ppi=400, max_bytes=10_000_000
    )
    assert (info.width, info.height) == (64, 96)
    assert info.dpi == (400.0, 400.0)
    assert info.has_icc


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (tiff_bytes(dpi=300), "ppi"),
        (tiff_bytes(icc=False), "ICC"),
        (tiff_bytes(mode="L"), "RGB"),
        (b"\x89PNG\r\n\x1a\n" + b"\x00" * 32, "magic"),
    ],
)
def test_sec_17_specification_failures_are_named(data: bytes, message: str) -> None:
    with pytest.raises(MasterValidationError, match=message):
        validate_master(
            data,
            expected_sha256=hashlib.sha256(data).hexdigest(),
            min_ppi=400,
            max_bytes=10_000_000,
        )


def test_sec_17_size_and_checksum_limits() -> None:
    data = tiff_bytes()
    with pytest.raises(MasterValidationError, match="exceeds"):
        validate_master(data, expected_sha256="0" * 64, min_ppi=400, max_bytes=10)
    with pytest.raises(MasterValidationError, match="checksum"):
        validate_master(data, expected_sha256="0" * 64, min_ppi=400, max_bytes=10_000_000)


def test_chunk_text_respects_line_boundaries() -> None:
    text = "\n".join(f"سطر رقم {i} في الصفحة" for i in range(30))
    chunks = chunk_text(text, 100)
    assert len(chunks) > 1
    assert all(len(c) <= 120 for c in chunks)
    assert "\n".join(chunks) == text


def test_derivatives_are_produced_in_both_formats() -> None:
    master = tiff_bytes(size=(300, 400))
    jp2 = access_derivative(master, "jp2")
    assert jp2.startswith(b"\x00\x00\x00\x0cjP")
    ptif = access_derivative(master, "ptif")
    assert ptif[:4] in (b"II*\x00", b"MM\x00*")
    thumb = webp_resized(master, 150, mark=False)
    assert thumb.startswith(b"RIFF")
    with Image.open(io.BytesIO(thumb)) as image:
        assert image.size == (150, 200)


def test_sec_14_platform_mark_changes_the_image() -> None:
    plain = Image.new("RGB", (600, 800), (240, 230, 210))
    marked = platform_mark(plain)
    assert marked.size == plain.size
    assert marked.tobytes() != plain.tobytes()
