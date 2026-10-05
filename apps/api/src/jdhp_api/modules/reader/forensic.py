"""Forensic (invisible) mark seeded per reader session (SEC-11, RDR-2, ADR-0006).

A blind spread-spectrum mark in the DCT domain of 8 by 8 luminance blocks. The session key
seeds a pseudo-random sign pattern over the mid-band coefficients of every block; embedding
nudges each coefficient in the pattern's direction, detection correlates the coefficients
with the pattern and reports a z-score. Under no mark the score is a standard normal; a
marked tile scores far above the threshold even after the WebP or JPEG re-encoding a leaked
tile goes through. The scheme is written with numpy only, so the gateway carries no OpenCV
or deep-learning runtime, and it is deterministic for a key, so the detector needs nothing
but the master key and the session id to re-derive the pattern.

Geometric attacks (scaling, unaligned crops, screenshots of a zoomed viewer) desynchronize
the 8 by 8 grid and need a search step the detector does not have yet; ADR-0006 records this
as the known limit of the Phase 1 mark.
"""

from __future__ import annotations

import dataclasses
import hashlib

import numpy as np
import pyvips
from numpy.typing import NDArray

BLOCK = 8
# Mid-band positions in the 8x8 DCT (zigzag order 6 to 17): low enough to survive
# re-encoding, high enough to stay invisible.
MID_BAND: tuple[tuple[int, int], ...] = (
    (0, 3),
    (1, 2),
    (2, 1),
    (3, 0),
    (4, 0),
    (3, 1),
    (2, 2),
    (1, 3),
    (0, 4),
    (0, 5),
    (1, 4),
    (2, 3),
)
STRENGTH = 0.12  # relative nudge of each marked coefficient
FLOOR = 2.5  # absolute nudge so flat regions carry the mark too (in 0..255 DCT units)
DETECTION_THRESHOLD = 6.0  # z-score; a false positive at this level is a ten-sigma-class event
LUMA = np.array([0.299, 0.587, 0.114], dtype=np.float64)


@dataclasses.dataclass(frozen=True, slots=True)
class Detection:
    score: float
    blocks: int

    @property
    def present(self) -> bool:
        return self.score >= DETECTION_THRESHOLD


def _dct_matrix(n: int = BLOCK) -> NDArray[np.float64]:
    k = np.arange(n)[:, None]
    i = np.arange(n)[None, :]
    matrix = np.asarray(
        np.cos(np.pi * (2 * i + 1) * k / (2 * n)) * np.sqrt(2 / n), dtype=np.float64
    )
    matrix[0, :] = np.sqrt(1 / n)
    return matrix


_D = _dct_matrix()
_DT = _D.T


def _blocks(y: NDArray[np.float64]) -> NDArray[np.float64]:
    """Reshape a padded luminance plane into (rows, cols, 8, 8) blocks."""
    h, w = y.shape
    return np.asarray(
        y.reshape(h // BLOCK, BLOCK, w // BLOCK, BLOCK).swapaxes(1, 2), dtype=np.float64
    )


def _unblocks(blocks: NDArray[np.float64]) -> NDArray[np.float64]:
    rows, cols, _, _ = blocks.shape
    return blocks.swapaxes(1, 2).reshape(rows * BLOCK, cols * BLOCK)


def _dct(blocks: NDArray[np.float64]) -> NDArray[np.float64]:
    return np.asarray(
        np.einsum("ij,rcjk,kl->rcil", _D, blocks, _DT, optimize=True), dtype=np.float64
    )


def _idct(coeffs: NDArray[np.float64]) -> NDArray[np.float64]:
    return np.asarray(
        np.einsum("ij,rcjk,kl->rcil", _DT, coeffs, _D, optimize=True), dtype=np.float64
    )


def _pattern(key: bytes, rows: int, cols: int) -> NDArray[np.float64]:
    """A +-1 pattern over (rows, cols, len(MID_BAND)) seeded by the session key."""
    seed = int.from_bytes(hashlib.sha256(b"jdhp forensic pattern v1" + key).digest()[:8], "big")
    rng = np.random.default_rng(seed)
    return rng.choice(np.array([-1.0, 1.0]), size=(rows, cols, len(MID_BAND)))


def _luminance(rgb: NDArray[np.float64]) -> NDArray[np.float64]:
    return rgb @ LUMA


def _pad(y: NDArray[np.float64]) -> tuple[NDArray[np.float64], int, int]:
    h, w = y.shape
    ph, pw = (-h) % BLOCK, (-w) % BLOCK
    return np.pad(y, ((0, ph), (0, pw)), mode="edge"), h, w


def _to_array(image: pyvips.Image) -> NDArray[np.float64]:
    rgb = (
        image
        if image.bands == 3
        else image.flatten()
        if image.hasalpha()
        else image.colourspace("srgb")
    )
    if rgb.bands != 3:  # pragma: no cover - every tile is sRGB by the time it is marked
        rgb = rgb.colourspace("srgb")
    return np.asarray(rgb.cast("uchar").numpy(), dtype=np.float64)


def embed(image: pyvips.Image, key: bytes) -> pyvips.Image:
    """Return ``image`` with the session's spread-spectrum mark in its luminance."""
    rgb = _to_array(image)
    y = _luminance(rgb)
    padded, h, w = _pad(y)
    blocks = _blocks(padded)
    coeffs = _dct(blocks)
    pattern = _pattern(key, *coeffs.shape[:2])
    rows_idx = np.array([u for u, _ in MID_BAND])
    cols_idx = np.array([v for _, v in MID_BAND])
    selected = coeffs[:, :, rows_idx, cols_idx]
    coeffs[:, :, rows_idx, cols_idx] = selected + pattern * (STRENGTH * np.abs(selected) + FLOOR)
    marked_y = _unblocks(_idct(coeffs))[:h, :w]
    delta = (marked_y - y)[:, :, None]
    out = np.clip(rgb + delta, 0, 255).astype(np.uint8)
    return pyvips.Image.new_from_array(out).copy(interpretation="srgb")


def detect(image: pyvips.Image, key: bytes) -> Detection:
    """Correlate the mid-band coefficients with the key's pattern; z-score under no mark."""
    y = _luminance(_to_array(image))
    padded, _, _ = _pad(y)
    coeffs = _dct(_blocks(padded))
    rows, cols = coeffs.shape[:2]
    pattern = _pattern(key, rows, cols)
    rows_idx = np.array([u for u, _ in MID_BAND])
    cols_idx = np.array([v for _, v in MID_BAND])
    selected = coeffs[:, :, rows_idx, cols_idx]
    # Normalize each coefficient so textured blocks do not drown flat ones.
    normalized = selected / (np.abs(selected) + FLOOR)
    products = normalized * pattern
    n = products.size
    score = float(products.sum() / (np.sqrt(n) * max(products.std(), 1e-9)))
    return Detection(score=score, blocks=rows * cols)
