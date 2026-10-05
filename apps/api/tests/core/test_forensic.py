"""The forensic mark (SEC-11): detected with its key, invisible, survives re-encoding."""

from __future__ import annotations

import pyvips

from jdhp_api.modules.reader import forensic

KEY = b"k" * 32
OTHER = b"o" * 32


def _tile() -> pyvips.Image:
    base = pyvips.Image.black(512, 512, bands=3).new_from_image([230, 220, 200])
    band = pyvips.Image.black(400, 40, bands=3).new_from_image([30, 25, 20])
    noise = pyvips.Image.gaussnoise(512, 512, mean=0, sigma=6).bandjoin(
        [pyvips.Image.gaussnoise(512, 512, mean=0, sigma=6)] * 2
    )
    return (base + noise).insert(band, 60, 200).cast("uchar").copy(interpretation="srgb")


def test_sec_11_mark_is_detected_with_its_key_only() -> None:
    tile = _tile()
    marked = forensic.embed(tile, KEY)
    assert (marked.width, marked.height, marked.bands) == (512, 512, 3)
    assert forensic.detect(marked, KEY).present
    assert not forensic.detect(marked, OTHER).present
    assert not forensic.detect(tile, KEY).present
    assert forensic.detect(tile, KEY).score < forensic.DETECTION_THRESHOLD / 2


def test_sec_11_mark_is_imperceptible_and_survives_web_re_encoding() -> None:
    tile = _tile()
    marked = forensic.embed(tile, KEY)
    delta = (marked.cast("int") - tile.cast("int")).abs()
    assert delta.avg() < 3.0, "the mark changes pixels by a hair on average"
    for data in (
        marked.webpsave_buffer(Q=80),
        marked.webpsave_buffer(Q=60),
        marked.jpegsave_buffer(Q=75),
    ):
        recoded = pyvips.Image.new_from_buffer(data, "")
        assert forensic.detect(recoded, KEY).present
        assert not forensic.detect(recoded, OTHER).present
    gray = marked.colourspace("b-w").colourspace("srgb")
    assert forensic.detect(gray, KEY).present


def test_sec_11_mark_handles_odd_sizes_and_alpha() -> None:
    odd = _tile().crop(0, 0, 501, 333).bandjoin(255)
    marked = forensic.embed(odd, KEY)
    assert (marked.width, marked.height) == (501, 333)
    assert forensic.detect(marked, KEY).present
