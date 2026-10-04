"""Preservation master validation (ADM-1, SEC-17): checksum, magic bytes, format, specification."""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass

from PIL import Image

TIFF_MAGIC = (b"II*\x00", b"MM\x00*")
MAX_DIMENSION = 20_000


class MasterValidationError(ValueError):
    """The staged image does not meet the preservation master specification."""


@dataclass(frozen=True, slots=True)
class MasterInfo:
    sha256: str
    width: int
    height: int
    dpi: tuple[float, float]
    has_icc: bool
    size: int


def validate_master(
    data: bytes, *, expected_sha256: str, min_ppi: int, max_bytes: int
) -> MasterInfo:
    if len(data) > max_bytes:
        msg = f"master exceeds {max_bytes} bytes"
        raise MasterValidationError(msg)
    if data[:4] not in TIFF_MAGIC:
        msg = "master is not a TIFF (magic bytes)"
        raise MasterValidationError(msg)
    digest = hashlib.sha256(data).hexdigest()
    if digest != expected_sha256.lower():
        msg = "checksum mismatch between manifest and staged file"
        raise MasterValidationError(msg)
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
        with Image.open(io.BytesIO(data)) as image:
            image_format = image.format
            mode = image.mode
            width, height = image.size
            dpi = image.info.get("dpi")
            icc = image.info.get("icc_profile")
    except Exception as exc:  # Pillow raises many exception types for malformed files
        msg = f"master cannot be decoded: {exc.__class__.__name__}"
        raise MasterValidationError(msg) from exc
    if image_format != "TIFF":
        msg = f"master format is {image_format}, expected TIFF"
        raise MasterValidationError(msg)
    if mode != "RGB":
        msg = f"master mode is {mode}, expected 24-bit RGB"
        raise MasterValidationError(msg)
    if not (0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION):
        msg = f"master dimensions {width}x{height} are out of range"
        raise MasterValidationError(msg)
    if not dpi or min(float(dpi[0]), float(dpi[1])) < min_ppi:
        msg = f"master resolution {dpi} is below {min_ppi} ppi"
        raise MasterValidationError(msg)
    if not icc:
        msg = "master has no embedded ICC profile"
        raise MasterValidationError(msg)
    return MasterInfo(
        sha256=digest,
        width=width,
        height=height,
        dpi=(float(dpi[0]), float(dpi[1])),
        has_icc=True,
        size=len(data),
    )
