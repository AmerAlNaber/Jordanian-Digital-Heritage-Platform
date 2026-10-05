"""The platform mark baked into public sample derivatives (SEC-14).

The mark is rendered by libvips (Pango and HarfBuzz), the same library that writes the
derivative. Rendering it with Pillow's text layout broke inside the Celery prefork pool: in a
forked worker process with libvips loaded, the shaped glyph run came back with a corrupt size,
every sample derivative failed and the seed batch never reached ``ingested``. One text stack
per process removes the conflict; ``test_sec_14_platform_mark_renders_in_a_forked_worker``
keeps it that way.
"""

from __future__ import annotations

from importlib import resources

import pyvips

MARK_AR = "منصة التراث الأردني الرقمي"
MARK_LATIN = "Jordanian Digital Heritage Platform"
INK = (60, 50, 40)
OPACITY_AR = 46
OPACITY_LATIN = 36
ANGLE_DEGREES = 18
SRGB = "srgb"


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


def _block(size: int) -> pyvips.Image:
    """Both lines of the mark, the Arabic line above the Latin one."""
    arabic = _glyphs(MARK_AR, size, OPACITY_AR)
    latin = _glyphs(MARK_LATIN, size, OPACITY_LATIN)
    latin_top = arabic.height + 4
    width = max(arabic.width, latin.width)
    height = latin_top + latin.height
    return _transparent(width, height).composite(
        [arabic, latin], "over", x=[width - arabic.width, 0], y=[0, latin_top]
    )


def _pattern(block: pyvips.Image, step: int, width: int, height: int) -> pyvips.Image:
    """The block repeated in a brick pattern: every ``step`` rows, odd rows shifted by half."""
    brick_w, brick_h = step * 2, step * 2
    # The second instance sits half a brick in; the part that overflows wraps to the left edge
    # so the replicated pattern is seamless.
    brick = _transparent(brick_w, brick_h).composite(
        [block, block, block], "over", x=[0, step, step - brick_w], y=[0, step, step]
    )
    across = -(-width // brick_w) + 1
    down = -(-height // brick_h) + 1
    return brick.replicate(across, down).crop(0, 0, width, height)


def platform_mark(image: pyvips.Image) -> pyvips.Image:
    """A repeated translucent diagonal mark. Visible but not obstructive.

    The result has the size and bands of ``image``. The pattern is drawn on a canvas larger
    than the image and rotated before it is cropped, so the corners carry the mark too.
    """
    size = max(14, image.width // 28)
    step = size * 9
    pad = max(image.width, image.height) // 2
    canvas_w, canvas_h = image.width + 2 * pad, image.height + 2 * pad
    pattern = _pattern(_block(size), step, canvas_w, canvas_h)
    rotated = pattern.rotate(ANGLE_DEGREES)
    left = (rotated.width - image.width) // 2
    top = (rotated.height - image.height) // 2
    mark = rotated.crop(left, top, image.width, image.height)
    has_alpha = image.hasalpha()
    base = image if has_alpha else image.bandjoin(255)
    marked = base.copy(interpretation=SRGB).composite2(mark, "over")
    return marked if has_alpha else marked.extract_band(0, n=3)
