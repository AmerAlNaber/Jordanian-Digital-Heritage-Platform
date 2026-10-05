"""Unit tests for validation, chunking, derivatives and the watermark."""

from __future__ import annotations

import hashlib
import io
import subprocess
import sys
from typing import Any

import pytest
import pyvips
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


def _parchment(width: int, height: int) -> pyvips.Image:
    return (
        pyvips.Image.black(width, height, bands=3)
        .new_from_image([240, 230, 210])
        .copy(interpretation="srgb")
    )


def test_sec_14_platform_mark_changes_the_image() -> None:
    plain = _parchment(600, 800)
    marked = platform_mark(plain)
    assert (marked.width, marked.height, marked.bands) == (600, 800, 3)
    assert marked.write_to_memory() != plain.write_to_memory()
    # The pattern is drawn larger than the image and rotated, so every quarter carries ink.
    for left, top in ((0, 0), (300, 0), (0, 400), (300, 400)):
        quarter = marked.crop(left, top, 300, 400)
        assert quarter.write_to_memory() != plain.crop(left, top, 300, 400).write_to_memory()


def test_sec_14_sample_is_marked_and_thumbnail_is_not() -> None:
    master = tiff_bytes(size=(300, 400))
    thumb = webp_resized(master, 300, mark=False)
    sample = webp_resized(master, 300, mark=True)
    assert sample.startswith(b"RIFF")
    assert thumb.startswith(b"RIFF")
    assert (
        pyvips.Image.new_from_buffer(sample, "").avg()
        != pyvips.Image.new_from_buffer(thumb, "").avg()
    )


FORKED_RENDER = """
import multiprocessing
import sys

import pyvips  # noqa: F401 - the Celery parent loads libvips through the task modules, then forks

from jdhp_worker.pipeline.derivatives import webp_resized


def render(conn, master):
    try:
        conn.send(("ok", str(len(webp_resized(master, 1200, mark=True)))))
    except Exception as exc:
        conn.send(("error", f"{exc.__class__.__name__}: {exc}"))


if __name__ == "__main__":
    master = sys.stdin.buffer.read()
    context = multiprocessing.get_context("fork")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(target=render, args=(child, master))
    process.start()
    child.close()
    outcome, detail = parent.recv()
    process.join(60)
    print(outcome, detail)
"""


@pytest.mark.skipif(sys.platform != "linux", reason="the Celery prefork pool forks on Linux")
def test_sec_14_platform_mark_renders_in_a_forked_worker() -> None:
    """Regression: with libvips loaded in the parent, the mark must still render after a fork.

    Pillow's text layout returned a corrupt glyph run in forked Celery workers, so every
    public sample failed and the seed batch never finished. The mark is rendered by libvips.
    The scenario runs in a fresh interpreter because libvips, once it has run an operation in
    a process, is not safe to fork; the Celery parent only imports it.
    """
    master = tiff_bytes(size=(945, 1418))
    result = subprocess.run(  # noqa: S603  # nosec B603  # fixed interpreter and script, no user input
        [sys.executable, "-c", FORKED_RENDER],
        input=master,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr.decode()
    outcome, _, detail = result.stdout.decode().strip().partition(" ")
    assert outcome == "ok", detail
    assert int(detail) > 0
