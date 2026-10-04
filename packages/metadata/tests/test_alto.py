"""ALTO round trip, offsets for highlights (CAT-4), and parser hardening (SEC-17)."""

from __future__ import annotations

import pytest

from jdhp_metadata import alto
from jdhp_metadata.xml_security import UnsafeXmlError, parse_xml


def sample_page() -> alto.AltoPage:
    lines = (
        alto.line_from_text("أخبار بلدة سُميرة", x=100, y=200, w=1200, h=60, confidence=0.97),
        alto.line_from_text(
            "وما حولها من الوادي والجبل", x=100, y=300, w=1200, h=60, confidence=0.91
        ),
    )
    return alto.AltoPage(
        width=1890, height=2835, lines=lines, engine="mock-ocr", engine_version="1"
    )


def test_round_trip_preserves_words_boxes_and_confidence() -> None:
    page = sample_page()
    xml = alto.to_alto_xml(page)
    assert b"alto/ns-v4" in xml
    parsed = alto.from_alto_xml(xml)
    assert alto.plain_text(parsed) == alto.plain_text(page)
    assert [w.x for w in parsed.words] == [w.x for w in page.words]
    assert parsed.engine == "mock-ocr"
    assert parsed.average_confidence() == pytest.approx(page.average_confidence(), abs=0.001)
    assert parsed.min_confidence() == pytest.approx(0.91, abs=0.001)


def test_cat_4_offsets_map_points_from_text_to_boxes() -> None:
    page = sample_page()
    text = alto.plain_text(page)
    offsets = alto.offsets_map(page)
    assert len(offsets) == len(page.words)
    for offset, word in zip(offsets, page.words, strict=True):
        assert text[offset.start : offset.end] == word.text
    start = text.index("الوادي")
    boxes = alto.boxes_for_range(offsets, start, start + len("الوادي"))
    assert len(boxes) == 1
    assert boxes[0].y == 300


def test_rtl_lines_place_the_first_word_at_the_right_edge() -> None:
    line = alto.line_from_text("كلمة أولى ثانية", x=0, y=0, w=300, h=20)
    assert line.words[0].x > line.words[-1].x


def test_sec_17_xml_parsers_reject_external_entities() -> None:
    evil = b"""<?xml version="1.0"?>
<!DOCTYPE alto [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<alto xmlns="http://www.loc.gov/standards/alto/ns-v4#"><Layout>
<Page ID="p" WIDTH="1" HEIGHT="1">&xxe;</Page></Layout></alto>"""
    with pytest.raises(UnsafeXmlError):
        parse_xml(evil)
    with pytest.raises(UnsafeXmlError):
        alto.from_alto_xml(evil)


def test_sec_17_entity_expansion_bomb_is_rejected() -> None:
    bomb = b"""<?xml version="1.0"?>
<!DOCTYPE lolz [<!ENTITY lol "lol">
<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">]>
<alto>&lol2;</alto>"""
    with pytest.raises(UnsafeXmlError):
        parse_xml(bomb)


def test_empty_page_has_zero_confidence_and_no_offsets() -> None:
    page = alto.AltoPage(width=10, height=10, lines=())
    assert page.average_confidence() == 0.0
    assert alto.offsets_map(page) == []
    assert alto.from_alto_xml(alto.to_alto_xml(page)).lines == ()
