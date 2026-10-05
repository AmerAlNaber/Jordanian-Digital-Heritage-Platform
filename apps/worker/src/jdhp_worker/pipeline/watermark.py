"""The platform mark baked into public sample derivatives (SEC-14).

The implementation lives in the API's reader module, where the tile gateway uses the same
libvips rendering for its per-reader marks; the worker calls it so samples and tiles carry
one mark. Rendering with Pillow's text layout broke inside the Celery prefork pool (a forked
child with libvips loaded returned a corrupt glyph run), which
``test_sec_14_platform_mark_renders_in_a_forked_worker`` guards against.
"""

from __future__ import annotations

from jdhp_api.modules.reader.watermark import (
    PLATFORM_MARK_AR as MARK_AR,
)
from jdhp_api.modules.reader.watermark import (
    PLATFORM_MARK_LATIN as MARK_LATIN,
)
from jdhp_api.modules.reader.watermark import (
    platform_mark,
)

__all__ = ["MARK_AR", "MARK_LATIN", "platform_mark"]
