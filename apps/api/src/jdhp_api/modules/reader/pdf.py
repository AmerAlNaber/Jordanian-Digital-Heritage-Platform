"""A minimal PDF writer for prints: one JPEG per page and nothing else (RDR-4).

The platform writes its own PDFs so the API and worker images carry no PDF engine. Each page
is one image XObject with the DCTDecode filter, which embeds the JPEG bytes unchanged, so the
marks the renderer applied are exactly what the file holds. No text layer, no fonts, no links
(CAT-4): the page image is the whole page.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
from collections.abc import Sequence

PDF_HEADER = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
POINTS_PER_INCH = 72


@dataclasses.dataclass(frozen=True, slots=True)
class PdfImage:
    jpeg: bytes
    width: int
    height: int
    gray: bool = False


def _text(value: str) -> bytes:
    """A PDF text string in UTF-16BE with a byte order mark, hex encoded: any script."""
    return b"<" + ("﻿" + value).encode("utf-16-be").hex().encode("ascii") + b">"


def _date(at: dt.datetime) -> bytes:
    return b"(D:" + at.astimezone(dt.UTC).strftime("%Y%m%d%H%M%S").encode("ascii") + b"Z)"


def points(pixels: int, ppi: int) -> float:
    return round(pixels * POINTS_PER_INCH / ppi, 2)


def build_pdf(
    images: Sequence[PdfImage],
    *,
    ppi: int,
    title: str,
    subject: str,
    producer: str,
    created_at: dt.datetime,
) -> bytes:
    """Serialize ``images`` as a PDF whose pages are sized so the images print at ``ppi``."""
    if not images:
        msg = "a print needs at least one page"
        raise ValueError(msg)
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    catalog = add(b"")
    pages = add(b"")
    info = add(
        b"<< /Title "
        + _text(title)
        + b" /Subject "
        + _text(subject)
        + b" /Producer "
        + _text(producer)
        + b" /Creator "
        + _text(producer)
        + b" /CreationDate "
        + _date(created_at)
        + b" >>"
    )
    page_numbers: list[int] = []
    for image in images:
        width_pt, height_pt = points(image.width, ppi), points(image.height, ppi)
        colorspace = b"/DeviceGray" if image.gray else b"/DeviceRGB"
        image_number = add(
            b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace %s "
            b"/BitsPerComponent 8 /Filter /DCTDecode /Interpolate true /Length %d >>\nstream\n"
            % (image.width, image.height, colorspace, len(image.jpeg))
            + image.jpeg
            + b"\nendstream"
        )
        content = f"q {width_pt} 0 0 {height_pt} 0 0 cm /Im0 Do Q".encode("ascii")
        content_number = add(
            b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream"
        )
        page_numbers.append(
            add(
                (
                    f"<< /Type /Page /Parent {pages} 0 R /MediaBox [0 0 {width_pt} {height_pt}] "
                    f"/Resources << /XObject << /Im0 {image_number} 0 R >> >> "
                    f"/Contents {content_number} 0 R >>"
                ).encode("ascii")
            )
        )
    objects[pages - 1] = (
        b"<< /Type /Pages /Kids ["
        + b" ".join(b"%d 0 R" % number for number in page_numbers)
        + b"] /Count %d >>" % len(page_numbers)
    )
    objects[catalog - 1] = (
        b"<< /Type /Catalog /Pages %d 0 R /ViewerPreferences << /DisplayDocTitle true >> >>" % pages
    )

    out = bytearray(PDF_HEADER)
    offsets: list[int] = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1,
        catalog,
        info,
        xref,
    )
    return bytes(out)
