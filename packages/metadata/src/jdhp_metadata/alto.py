"""ALTO 4 for OCR output: word coordinates for search highlighting, plain text for indexing.

The platform keeps ALTO because highlights on the scan come from word boxes (CAT-4). The plain
text derived here is internal and never rendered.
"""

from __future__ import annotations

import datetime as dt
import xml.etree.ElementTree as ET  # nosec B405  # build only; parsing uses xml_security
from dataclasses import dataclass

from jdhp_metadata.xml_security import parse_xml

ALTO_NS = "http://www.loc.gov/standards/alto/ns-v4#"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
ALTO_SCHEMA = "http://www.loc.gov/standards/alto/v4/alto-4-2.xsd"


@dataclass(frozen=True, slots=True)
class Word:
    text: str
    x: int
    y: int
    w: int
    h: int
    confidence: float = 1.0


@dataclass(frozen=True, slots=True)
class Line:
    words: tuple[Word, ...]
    x: int
    y: int
    w: int
    h: int

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)


@dataclass(frozen=True, slots=True)
class AltoPage:
    width: int
    height: int
    lines: tuple[Line, ...]
    language: str = "ara"
    engine: str = "unknown"
    engine_version: str = "0"
    processed_at: dt.datetime | None = None
    page_id: str = "page"

    @property
    def words(self) -> tuple[Word, ...]:
        return tuple(word for line in self.lines for word in line.words)

    def average_confidence(self) -> float:
        words = self.words
        return sum(w.confidence for w in words) / len(words) if words else 0.0

    def min_confidence(self) -> float:
        words = self.words
        return min(w.confidence for w in words) if words else 0.0


def plain_text(page: AltoPage) -> str:
    """Lines joined by newlines, words by single spaces. Offsets refer to this string."""
    return "\n".join(line.text for line in page.lines)


@dataclass(frozen=True, slots=True)
class Offset:
    start: int
    end: int
    x: int
    y: int
    w: int
    h: int

    def as_dict(self) -> dict[str, int]:
        return {
            "start": self.start,
            "end": self.end,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
        }


def offsets_map(page: AltoPage) -> list[Offset]:
    """Character offsets in plain_text(page) to word boxes, in reading order."""
    offsets: list[Offset] = []
    cursor = 0
    for line_index, line in enumerate(page.lines):
        if line_index:
            cursor += 1  # the newline between lines
        for word_index, word in enumerate(line.words):
            if word_index:
                cursor += 1  # the space between words
            offsets.append(Offset(cursor, cursor + len(word.text), word.x, word.y, word.w, word.h))
            cursor += len(word.text)
    return offsets


def boxes_for_range(offsets: list[Offset], start: int, end: int) -> list[Offset]:
    """Word boxes overlapping a character range; what a highlight on the scan is drawn from."""
    return [o for o in offsets if o.start < end and o.end > start]


def to_alto_xml(page: AltoPage) -> bytes:
    ET.register_namespace("", ALTO_NS)
    ET.register_namespace("xsi", XSI_NS)
    root = ET.Element(
        f"{{{ALTO_NS}}}alto", {f"{{{XSI_NS}}}schemaLocation": f"{ALTO_NS} {ALTO_SCHEMA}"}
    )
    description = ET.SubElement(root, f"{{{ALTO_NS}}}Description")
    ET.SubElement(description, f"{{{ALTO_NS}}}MeasurementUnit").text = "pixel"
    step = ET.SubElement(description, f"{{{ALTO_NS}}}OCRProcessing", {"ID": "ocr"})
    processing = ET.SubElement(step, f"{{{ALTO_NS}}}ocrProcessingStep")
    if page.processed_at is not None:
        ET.SubElement(
            processing, f"{{{ALTO_NS}}}processingDateTime"
        ).text = page.processed_at.isoformat()
    software = ET.SubElement(processing, f"{{{ALTO_NS}}}processingSoftware")
    ET.SubElement(software, f"{{{ALTO_NS}}}softwareName").text = page.engine
    ET.SubElement(software, f"{{{ALTO_NS}}}softwareVersion").text = page.engine_version
    layout = ET.SubElement(root, f"{{{ALTO_NS}}}Layout")
    page_el = ET.SubElement(
        layout,
        f"{{{ALTO_NS}}}Page",
        {
            "ID": page.page_id,
            "PHYSICAL_IMG_NR": "1",
            "WIDTH": str(page.width),
            "HEIGHT": str(page.height),
        },
    )
    space = ET.SubElement(
        page_el,
        f"{{{ALTO_NS}}}PrintSpace",
        {"HPOS": "0", "VPOS": "0", "WIDTH": str(page.width), "HEIGHT": str(page.height)},
    )
    block = ET.SubElement(
        space,
        f"{{{ALTO_NS}}}TextBlock",
        {
            "ID": "block_1",
            "HPOS": "0",
            "VPOS": "0",
            "WIDTH": str(page.width),
            "HEIGHT": str(page.height),
            "LANG": page.language,
        },
    )
    for line_index, line in enumerate(page.lines, start=1):
        line_el = ET.SubElement(
            block,
            f"{{{ALTO_NS}}}TextLine",
            {
                "ID": f"line_{line_index}",
                "HPOS": str(line.x),
                "VPOS": str(line.y),
                "WIDTH": str(line.w),
                "HEIGHT": str(line.h),
            },
        )
        for word_index, word in enumerate(line.words, start=1):
            if word_index > 1:
                ET.SubElement(
                    line_el,
                    f"{{{ALTO_NS}}}SP",
                    {"HPOS": str(word.x), "VPOS": str(word.y), "WIDTH": "1"},
                )
            ET.SubElement(
                line_el,
                f"{{{ALTO_NS}}}String",
                {
                    "ID": f"string_{line_index}_{word_index}",
                    "CONTENT": word.text,
                    "HPOS": str(word.x),
                    "VPOS": str(word.y),
                    "WIDTH": str(word.w),
                    "HEIGHT": str(word.h),
                    "WC": f"{word.confidence:.3f}",
                },
            )
    return bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))


def from_alto_xml(data: bytes | str) -> AltoPage:
    root = parse_xml(data)
    ns = {"a": ALTO_NS}
    page_el = root.find(".//a:Page", ns)
    if page_el is None:
        msg = "ALTO document has no Page element"
        raise ValueError(msg)
    engine = root.findtext(".//a:softwareName", default="unknown", namespaces=ns)
    version = root.findtext(".//a:softwareVersion", default="0", namespaces=ns)
    language = "ara"
    block = root.find(".//a:TextBlock", ns)
    if block is not None and block.get("LANG"):
        language = str(block.get("LANG"))
    lines: list[Line] = []
    for line_el in root.findall(".//a:TextLine", ns):
        words = tuple(
            Word(
                text=str(s.get("CONTENT", "")),
                x=int(s.get("HPOS", "0")),
                y=int(s.get("VPOS", "0")),
                w=int(s.get("WIDTH", "0")),
                h=int(s.get("HEIGHT", "0")),
                confidence=float(s.get("WC", "1.0")),
            )
            for s in line_el.findall("a:String", ns)
        )
        lines.append(
            Line(
                words=words,
                x=int(line_el.get("HPOS", "0")),
                y=int(line_el.get("VPOS", "0")),
                w=int(line_el.get("WIDTH", "0")),
                h=int(line_el.get("HEIGHT", "0")),
            )
        )
    return AltoPage(
        width=int(page_el.get("WIDTH", "0")),
        height=int(page_el.get("HEIGHT", "0")),
        lines=tuple(lines),
        language=language,
        engine=engine,
        engine_version=version,
        page_id=str(page_el.get("ID", "page")),
    )


def line_from_text(
    text: str, *, x: int, y: int, w: int, h: int, confidence: float = 1.0, rtl: bool = True
) -> Line:
    """Split a line of text into words with boxes proportional to their length."""
    tokens = [t for t in text.split(" ") if t]
    if not tokens:
        return Line(words=(), x=x, y=y, w=w, h=h)
    total = sum(len(t) for t in tokens) + (len(tokens) - 1)
    words: list[Word] = []
    cursor = 0
    for token in tokens:
        width = max(1, round(w * len(token) / total))
        start = x + round(w * cursor / total)
        word_x = x + w - (start - x) - width if rtl else start
        words.append(Word(text=token, x=max(x, word_x), y=y, w=width, h=h, confidence=confidence))
        cursor += len(token) + 1
    return Line(words=tuple(words), x=x, y=y, w=w, h=h)
