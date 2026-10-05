"""Visible marks on every image that leaves the platform (SEC-11, SEC-14).

Rendered with libvips (Pango) so the text stack is the same one that cuts the tile. The
pattern repeats along a diagonal at low opacity so any crop still carries an instance; it is
drawn on a padded canvas and rotated before cropping so the corners carry it too.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Sequence
from importlib import resources

import pyvips

PLATFORM_MARK_AR = "منصة التراث الأردني الرقمي"
PLATFORM_MARK_LATIN = "Jordanian Digital Heritage Platform"
INK = (60, 50, 40)
OPACITY_PRIMARY = 46
OPACITY_SECONDARY = 36
ANGLE_DEGREES = 18
SRGB = "srgb"
MIN_SIZE = 14


def _font_file() -> str:
    return str(resources.files("jdhp_api.seed.fonts").joinpath("Amiri-Regular.ttf"))


def _glyphs(text: str, size: int, opacity: int) -> pyvips.Image:
    """The text as a translucent RGBA image: Pango's coverage, scaled to ``opacity``, as alpha."""
    rendered = pyvips.Image.text(
        text, font=f"Amiri {size}", fontfile=_font_file(), rgba=True, dpi=72
    )
    coverage = rendered[3] * (opacity / 255)
    ink = rendered.new_from_image(list(INK))
    return ink.bandjoin(coverage).cast("uchar").copy(interpretation=SRGB)


def _transparent(width: int, height: int) -> pyvips.Image:
    return pyvips.Image.black(width, height, bands=4).copy(interpretation=SRGB)


def _block(lines: Sequence[tuple[str, int]], size: int) -> pyvips.Image:
    """The lines of the mark stacked, right-aligned so Arabic and Latin lines share an edge."""
    glyphs = [_glyphs(text, size, opacity) for text, opacity in lines]
    width = max(g.width for g in glyphs)
    gap = max(2, size // 10)
    height = sum(g.height for g in glyphs) + gap * (len(glyphs) - 1)
    xs: list[int] = []
    ys: list[int] = []
    top = 0
    for g in glyphs:
        xs.append(width - g.width)
        ys.append(top)
        top += g.height + gap
    return _transparent(width, height).composite(glyphs, "over", x=xs, y=ys)


def _pattern(block: pyvips.Image, step: int, width: int, height: int) -> pyvips.Image:
    """The block repeated in a brick pattern: every ``step`` rows, odd rows shifted by half."""
    brick_w, brick_h = step * 2, step * 2
    brick = _transparent(brick_w, brick_h).composite(
        [block, block, block], "over", x=[0, step, step - brick_w], y=[0, step, step]
    )
    across = -(-width // brick_w) + 1
    down = -(-height // brick_h) + 1
    return brick.replicate(across, down).crop(0, 0, width, height)


def diagonal_mark(
    image: pyvips.Image, lines: Sequence[tuple[str, int]], *, size: int | None = None
) -> pyvips.Image:
    """Repeat ``lines`` (text, opacity) diagonally over ``image``; same size and bands out."""
    size = size or max(MIN_SIZE, image.width // 28)
    step = size * 9
    pad = max(image.width, image.height) // 2
    canvas_w, canvas_h = image.width + 2 * pad, image.height + 2 * pad
    pattern = _pattern(_block(lines, size), step, canvas_w, canvas_h)
    rotated = pattern.rotate(ANGLE_DEGREES)
    left = (rotated.width - image.width) // 2
    top = (rotated.height - image.height) // 2
    mark = rotated.crop(left, top, image.width, image.height)
    has_alpha = image.hasalpha()
    base = image if has_alpha else image.bandjoin(255)
    marked = base.copy(interpretation=SRGB).composite2(mark, "over")
    return marked if has_alpha else marked.extract_band(0, n=3)


def platform_mark(image: pyvips.Image) -> pyvips.Image:
    """The platform's own mark for public samples and open works (SEC-14)."""
    return diagonal_mark(
        image, [(PLATFORM_MARK_AR, OPACITY_PRIMARY), (PLATFORM_MARK_LATIN, OPACITY_SECONDARY)]
    )


def session_mark(
    image: pyvips.Image,
    *,
    user_tag: str,
    session_public_id: str,
    work_public_id: str,
    at: dt.datetime | None = None,
) -> pyvips.Image:
    """The per-reader mark on every protected tile: who, when and which work (RDR-2, SEC-11).

    ``user_tag`` is a public identifier, never an email. Tiles are small, so the mark is set
    at a size that stays legible on a 512 pixel tile.
    """
    stamp = (at or dt.datetime.now(dt.UTC)).strftime("%Y-%m-%dT%H:%MZ")
    size = max(MIN_SIZE, image.width // 24)
    return diagonal_mark(
        image,
        [
            (f"{user_tag} · {stamp}", OPACITY_PRIMARY),
            (f"{work_public_id} · {session_public_id}", OPACITY_SECONDARY),
        ],
        size=size,
    )
