"""Render the seed book into synthetic preservation masters with OCR ground truth.

Output of ``python -m jdhp_api.seed.generate --out DIR [--scale S]``::

    DIR/master/0001.tif ...   uncompressed RGB TIFF, 400 ppi, embedded sRGB profile
    DIR/ground_truth/0001.json   width, height and every text line with its box and confidence
    DIR/manifest.json           an intake manifest (new_work, item, capture, pages with SHA-256)
    DIR/checksums.sha256        sha256sum-format fixity manifest

Everything is deterministic for a given scale, so fixtures and demos agree byte for byte.
The scans are synthetic: parchment tone, mottling, a few stains, and real Arabic type.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, assert_never

from PIL import Image, ImageChops, ImageCms, ImageDraw, ImageFont, features

from jdhp_api.seed.loader import SeedBlock, SeedPage, load_book
from jdhp_metadata.checksums import ChecksumEntry, format_manifest, sha256_file

PPI = 400
PAGE_WIDTH_PX = 1890  # 12 cm at 400 ppi
PAGE_HEIGHT_PX = 2835  # 18 cm at 400 ppi
PARCHMENT = (243, 234, 216)
INK = (38, 30, 26)
FAINT_INK = (110, 96, 84)
STAMP_INK = (54, 68, 120)
RAQM = features.check("raqm")

try:  # the fallback shaper when Pillow has no raqm
    import arabic_reshaper
    from bidi.algorithm import get_display
except ImportError:  # pragma: no cover - the seed extra installs both
    arabic_reshaper = None
    get_display = None


@dataclass(slots=True)
class TruthLine:
    text: str
    x: int
    y: int
    w: int
    h: int
    confidence: float

    def as_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "confidence": round(self.confidence, 3),
        }


def ibox(box: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    """Pillow returns float boxes; ground truth and ALTO want pixels."""
    left, top, right, bottom = box
    return int(left), int(top), int(right), int(bottom)


def _font_path(name: str) -> str:
    return str(resources.files("jdhp_api.seed.fonts").joinpath(name))


class Renderer:
    def __init__(self, scale: float = 1.0) -> None:
        self.scale = scale
        self.width = max(200, round(PAGE_WIDTH_PX * scale))
        self.height = max(300, round(PAGE_HEIGHT_PX * scale))
        self.margin_x = round(self.width * 0.11)
        self.margin_top = round(self.height * 0.09)
        self.body_size = max(10, round(self.width * 0.0265))
        self._fonts: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def font(self, size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
        key = ("bold" if bold else "regular", size)
        if key not in self._fonts:
            self._fonts[key] = ImageFont.truetype(
                _font_path("Amiri-Bold.ttf" if bold else "Amiri-Regular.ttf"), size
            )
        return self._fonts[key]

    @staticmethod
    def shape(text: str) -> tuple[str, dict[str, Any]]:
        """Return the string to draw and the extra kwargs for ImageDraw.text."""
        if RAQM:
            return text, {"direction": "rtl", "language": "ar"}
        if arabic_reshaper is not None and get_display is not None:
            return get_display(arabic_reshaper.reshape(text)), {}
        return text, {}

    def background(self, seq: int) -> Image.Image:
        rng = random.Random(seq * 7919 + 17)  # noqa: S311  # nosec B311  # visual variation only
        tone = (
            max(0, min(255, PARCHMENT[0] + rng.randint(-6, 6))),
            max(0, min(255, PARCHMENT[1] + rng.randint(-6, 6))),
            max(0, min(255, PARCHMENT[2] + rng.randint(-6, 6))),
        )
        page = Image.new("RGB", (self.width, self.height), tone)
        tile = 96
        noise = Image.frombytes(
            "L", (tile, tile), bytes(rng.randrange(205, 256) for _ in range(tile * tile))
        )
        noise = noise.resize((self.width, self.height), Image.Resampling.BICUBIC)
        page = ImageChops.multiply(page, Image.merge("RGB", (noise, noise, noise)))
        draw = ImageDraw.Draw(page, "RGBA")
        for _ in range(rng.randint(0, 3)):
            x, y = rng.randint(0, self.width), rng.randint(0, self.height)
            r = rng.randint(self.width // 40, self.width // 12)
            draw.ellipse((x - r, y - r, x + r, y + r), fill=(150, 120, 70, rng.randint(8, 22)))
        # a darker gutter on the inner (right) edge, as a scanned bound book shows
        gutter = Image.new("L", (self.width, 1), 255)
        gdraw = ImageDraw.Draw(gutter)
        for i in range(self.width // 12):
            gdraw.point((self.width - 1 - i, 0), fill=255 - int(60 * (1 - i / (self.width / 12))))
        gutter_rgb = gutter.resize((self.width, self.height))
        return ImageChops.multiply(page, Image.merge("RGB", (gutter_rgb, gutter_rgb, gutter_rgb)))

    def text_width(self, text: str, font: ImageFont.FreeTypeFont) -> tuple[int, int]:
        shaped, kwargs = self.shape(text)
        left, top, right, bottom = ibox(font.getbbox(shaped, **kwargs))
        return right - left, bottom - top

    def draw_line(
        self,
        draw: ImageDraw.ImageDraw,
        text: str,
        *,
        y: int,
        font: ImageFont.FreeTypeFont,
        align: str,
        fill: tuple[int, int, int] = INK,
        confidence: float,
        truth: list[TruthLine],
        rng: random.Random,
    ) -> int:
        shaped, kwargs = self.shape(text)
        width, _height = self.text_width(text, font)
        line_height = round(font.size * 1.75)
        if align == "center":
            x = (self.width - width) // 2
        elif align == "left":
            x = self.margin_x
        else:
            x = self.width - self.margin_x - width
        jitter = rng.randint(-1, 1)
        draw.text((x, y + jitter), shaped, font=font, fill=fill, **kwargs)
        left, top, right, bottom = ibox(draw.textbbox((x, y + jitter), shaped, font=font, **kwargs))
        truth.append(
            TruthLine(
                text=text,
                x=left,
                y=top,
                w=max(1, right - left),
                h=max(1, bottom - top),
                confidence=confidence,
            )
        )
        return y + line_height

    def confidence_for(self, page: SeedPage, rng: random.Random) -> float:
        base = (
            0.80 if page.seq == 25 else 0.955
        )  # page 25 is deliberately under the 85 percent flag
        return min(0.999, max(0.5, base + rng.uniform(-0.03, 0.03)))

    def render(self, page: SeedPage) -> tuple[Image.Image, list[TruthLine]]:
        image = self.background(page.seq)
        draw = ImageDraw.Draw(image)
        rng = random.Random(page.seq * 104729 + 3)  # noqa: S311  # nosec B311  # layout jitter only
        truth: list[TruthLine] = []
        y = self.margin_top
        if page.label:
            y = self.draw_line(
                draw,
                page.label,
                y=y,
                font=self.font(round(self.body_size * 0.9)),
                align="center",
                fill=FAINT_INK,
                confidence=self.confidence_for(page, rng),
                truth=truth,
                rng=rng,
            )
            y += round(self.body_size * 0.6)
        if page.type in {"cover", "title", "blank", "colophon"}:
            y += round(self.height * 0.14)
        for block in page.blocks:
            y = self.render_block(draw, block, page, y, truth, rng)
        return image, truth

    def render_block(  # noqa: PLR0911 - one return per block kind
        self,
        draw: ImageDraw.ImageDraw,
        block: SeedBlock,
        page: SeedPage,
        y: int,
        truth: list[TruthLine],
        rng: random.Random,
    ) -> int:
        conf = self.confidence_for(page, rng)
        if block.kind == "display":
            font = self.font(round(self.body_size * 2.1), bold=True)
            for line in block.lines:
                y = self.draw_line(
                    draw,
                    line,
                    y=y,
                    font=font,
                    align="center",
                    confidence=conf,
                    truth=truth,
                    rng=rng,
                )
            return y + round(self.body_size * 1.5)
        if block.kind == "center":
            font = self.font(round(self.body_size * 1.15))
            for line in block.lines:
                y = self.draw_line(
                    draw,
                    line,
                    y=y,
                    font=font,
                    align="center",
                    confidence=conf,
                    truth=truth,
                    rng=rng,
                )
            return y + round(self.body_size * 1.2)
        if block.kind == "heading":
            font = self.font(round(self.body_size * 1.45), bold=True)
            for line in block.lines:
                y = self.draw_line(
                    draw,
                    line,
                    y=y,
                    font=font,
                    align="center",
                    confidence=conf,
                    truth=truth,
                    rng=rng,
                )
            rule_w = round(self.width * 0.25)
            draw.line(
                ((self.width - rule_w) // 2, y, (self.width + rule_w) // 2, y),
                fill=INK,
                width=max(1, round(2 * self.scale)),
            )
            return y + round(self.body_size * 1.1)
        if block.kind == "body":
            font = self.font(self.body_size)
            for line in block.lines:
                y = self.draw_line(
                    draw, line, y=y, font=font, align="right", confidence=conf, truth=truth, rng=rng
                )
            return y + round(self.body_size * 0.8)
        if block.kind == "caption":
            font = self.font(round(self.body_size * 0.85))
            for line in block.lines:
                y = self.draw_line(
                    draw,
                    line,
                    y=y,
                    font=font,
                    align="center",
                    fill=FAINT_INK,
                    confidence=conf,
                    truth=truth,
                    rng=rng,
                )
            return y + round(self.body_size * 0.8)
        if block.kind == "figure":
            return self.render_figure(draw, block, page, y, truth, rng, conf)
        if block.kind == "table":
            return self.render_table(draw, block, y, truth, conf)
        if block.kind == "stamp":
            font = self.font(round(self.body_size * 0.8))
            box_w, box_h = (
                round(self.width * 0.42),
                round(self.body_size * 1.75 * (len(block.lines) + 0.6)),
            )
            x0, y0 = self.margin_x, self.height - self.margin_top - box_h
            draw.rounded_rectangle(
                (x0, y0, x0 + box_w, y0 + box_h),
                radius=round(8 * self.scale),
                outline=STAMP_INK,
                width=max(1, round(3 * self.scale)),
            )
            yy = y0 + round(self.body_size * 0.4)
            for line in block.lines:
                shaped, kwargs = self.shape(line)
                width, _ = self.text_width(line, font)
                x = x0 + (box_w - width) // 2
                draw.text((x, yy), shaped, font=font, fill=STAMP_INK, **kwargs)
                left, top, right, bottom = (
                    int(v) for v in draw.textbbox((x, yy), shaped, font=font, **kwargs)
                )
                truth.append(TruthLine(line, left, top, right - left, bottom - top, conf))
                yy += round(font.size * 1.75)
            return y
        assert_never(block.kind)

    def render_figure(
        self,
        draw: ImageDraw.ImageDraw,
        block: SeedBlock,
        page: SeedPage,
        y: int,
        truth: list[TruthLine],
        rng: random.Random,
        conf: float,
    ) -> int:
        x0, x1 = self.margin_x, self.width - self.margin_x
        y0, y1 = y, y + round(self.height * 0.42)
        lw = max(1, round(3 * self.scale))
        draw.rectangle((x0, y0, x1, y1), outline=INK, width=lw)
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        if page.type == "illustration":
            r = (x1 - x0) // 5
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=INK, width=lw)
            draw.ellipse(
                (cx - r // 6, cy - r // 6, cx + r // 6, cy + r // 6), outline=INK, width=lw
            )
            draw.rectangle((x0 + r // 2, y1 - r, x1 - r // 2, y1 - r // 3), outline=INK, width=lw)
            draw.line((cx, cy, cx + r * 7 // 5, cy - r * 3 // 5), fill=INK, width=lw)
            for i in range(5):
                bx = x0 + r // 2 + i * r // 2
                draw.arc((bx, y1 - r * 3 // 2, bx + r // 2, y1 - r), 180, 360, fill=INK, width=lw)
        else:  # map
            r_ = (x1 - x0) // 6
            points = [
                (x0 + (x1 - x0) * t / 20, cy + (y1 - y0) * 0.25 * ((t % 3) - 1) / 3)
                for t in range(21)
            ]
            draw.line(points, fill=INK, width=lw * 2)
            draw.polygon(
                [(x1 - r_, y0 + r_ * 2), (x1 - r_ // 2, y0 + r_), (x1 - r_ * 1.5, y0 + r_)],
                outline=INK,
                width=lw,
            )
            for i in range(9):
                hx = x0 + (x1 - x0) * 0.3 + (i % 3) * r_ // 3
                hy = cy - r_ // 2 + (i // 3) * r_ // 3
                draw.rectangle((hx, hy, hx + r_ // 5, hy + r_ // 5), outline=INK, width=lw)
            draw.ellipse(
                (x0 + r_ // 2, cy - r_ // 6, x0 + r_ // 2 + r_ // 3, cy + r_ // 6),
                outline=INK,
                width=lw,
            )
            for i in range(0, x1 - x0, max(8, round(24 * self.scale))):
                draw.line(
                    (x0 + i, y1 - r_ // 2, x0 + i + max(4, round(10 * self.scale)), y1 - r_ // 2),
                    fill=INK,
                    width=lw,
                )
        # figure title inside the frame
        font = self.font(round(self.body_size * 0.95), bold=True)
        yy = y0 + round(self.body_size * 0.5)
        for line in block.lines:
            yy = self.draw_line(
                draw, line, y=yy, font=font, align="center", confidence=conf, truth=truth, rng=rng
            )
        return y1 + round(self.body_size * 0.8)

    def render_table(
        self,
        draw: ImageDraw.ImageDraw,
        block: SeedBlock,
        y: int,
        truth: list[TruthLine],
        conf: float,
    ) -> int:
        columns = block.columns or []
        rows = block.rows or []
        if not columns:
            return y
        font = self.font(round(self.body_size * 0.82))
        bold = self.font(round(self.body_size * 0.82), bold=True)
        x0, x1 = self.margin_x, self.width - self.margin_x
        widths = [0.17, 0.14, 0.2, 0.2, 0.29]
        col_w = [round((x1 - x0) * w) for w in widths[: len(columns)]]
        row_h = round(font.size * 2.0)
        lw = max(1, round(2 * self.scale))

        def draw_row(cells: list[str], yy: int, fnt: ImageFont.FreeTypeFont) -> None:
            # right-to-left columns: the first column is at the right edge
            cx = x1
            for cell, w in zip(cells, col_w, strict=False):
                cx -= w
                draw.rectangle((cx, yy, cx + w, yy + row_h), outline=INK, width=lw)
                if cell:
                    shaped, kwargs = self.shape(cell)
                    tw, _ = self.text_width(cell, fnt)
                    tx = cx + (w - tw) // 2
                    ty = yy + round(font.size * 0.35)
                    draw.text((tx, ty), shaped, font=fnt, fill=INK, **kwargs)
                    left, top, right, bottom = ibox(
                        draw.textbbox((tx, ty), shaped, font=fnt, **kwargs)
                    )
                    truth.append(
                        TruthLine(cell, left, top, max(1, right - left), max(1, bottom - top), conf)
                    )

        draw_row(columns, y, bold)
        y += row_h
        for row in rows:
            draw_row(row, y, font)
            y += row_h
        return y + round(self.body_size * 0.8)


def srgb_profile_bytes() -> bytes:
    return ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()


def generate(out: Path, *, scale: float = 1.0, preview: bool = False) -> Path:
    book = load_book()
    renderer = Renderer(scale)
    masters = out / "master"
    truth_dir = out / "ground_truth"
    masters.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)
    if preview:
        (out / "preview").mkdir(exist_ok=True)
    icc = srgb_profile_bytes()
    entries: list[ChecksumEntry] = []
    manifest_pages: list[dict[str, Any]] = []
    for page in book.pages:
        image, truth = renderer.render(page)
        target = masters / page.filename
        image.save(target, format="TIFF", dpi=(PPI, PPI), compression=None, icc_profile=icc)
        if preview:
            image.convert("RGB").resize((image.width // 2, image.height // 2)).save(
                out / "preview" / f"{page.seq:04d}.png"
            )
        (truth_dir / f"{page.seq:04d}.json").write_text(
            json.dumps(
                {
                    "width": image.width,
                    "height": image.height,
                    "language": "ara",
                    "rtl": True,
                    "lines": [line.as_dict() for line in truth],
                },
                ensure_ascii=False,
                indent=1,
            ),
            "utf-8",
        )
        digest = sha256_file(target)
        entries.append(ChecksumEntry(digest, f"master/{page.filename}"))
        manifest_pages.append(
            {
                "seq": page.seq,
                "filename": page.filename,
                "sha256": digest,
                "label": page.label,
                "page_type": page.type,
                "language": "ara",
                "script": "Arab",
                "section_title": page.section,
                "description": None,
            }
        )
    (out / "checksums.sha256").write_text(format_manifest(entries), "utf-8")
    manifest = {
        "new_work": book.work.work_create_fields(),
        "item": book.item.model_dump(),
        "capture": {
            "device": book.capture.device,
            "captured_on": dt.date(2026, 9, 1).isoformat(),
            "color_target_ref": book.capture.color_target_ref,
            "operator": book.capture.operator,
        },
        "staging_prefix": "intake/seed-book",
        "pages": manifest_pages,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), "utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--scale", type=float, default=1.0, help="1.0 renders 400 ppi masters; 0.25 for tests"
    )
    parser.add_argument("--preview", action="store_true", help="also write half-size PNG previews")
    args = parser.parse_args(argv)
    generate(args.out, scale=args.scale, preview=args.preview)
    sys.stdout.write(f"seed book rendered to {args.out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
