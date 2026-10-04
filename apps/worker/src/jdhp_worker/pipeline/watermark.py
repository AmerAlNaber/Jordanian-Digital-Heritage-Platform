"""The platform mark baked into public sample derivatives (SEC-14)."""

from __future__ import annotations

from importlib import resources
from typing import Any

from PIL import Image, ImageDraw, ImageFont, features

MARK_AR = "منصة التراث الأردني الرقمي"
MARK_LATIN = "Jordanian Digital Heritage Platform"


def _font(size: int) -> ImageFont.FreeTypeFont:
    path = resources.files("jdhp_api.seed.fonts").joinpath("Amiri-Regular.ttf")
    return ImageFont.truetype(str(path), size)


def platform_mark(image: Image.Image) -> Image.Image:
    """A repeated translucent diagonal mark. Visible but not obstructive."""
    base = image.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    size = max(14, base.width // 28)
    font = _font(size)
    kwargs: dict[str, Any] = (
        {"direction": "rtl", "language": "ar"} if features.check("raqm") else {}
    )
    text = MARK_AR if kwargs else MARK_LATIN
    step = size * 9
    for y in range(size, base.height, step):
        for x in range(-base.width // 2, base.width, step * 2):
            draw.text(
                (x + (y // step % 2) * step, y), text, font=font, fill=(60, 50, 40, 46), **kwargs
            )
            draw.text(
                (x + (y // step % 2) * step, y + size + 4),
                MARK_LATIN,
                font=font,
                fill=(60, 50, 40, 36),
            )
    rotated = overlay.rotate(18, resample=Image.Resampling.BICUBIC, expand=False)
    return Image.alpha_composite(base, rotated).convert("RGB")
