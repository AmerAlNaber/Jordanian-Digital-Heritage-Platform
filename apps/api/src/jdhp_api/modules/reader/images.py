"""IIIF Image API 3.0 request parsing and the image sources behind the tile gateway.

Two sources implement the same small interface: ``CantaloupeSource`` proxies to the image
server named in SPEC.md with the signed internal header its delegate checks, and
``LibvipsSource`` reads the JPEG 2000 access derivative from the bucket and crops it with
libvips. ADR-0005 decides which one deployments run; tests run the libvips source.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import math
import re
import time
import urllib.parse
from typing import Protocol

import httpx
import pyvips

from jdhp_api.core.config import Settings
from jdhp_api.core.errors import TileRequestError, TileTooLargeError
from jdhp_api.core.storage import ObjectStore

QUALITIES = frozenset({"default", "color", "gray"})
FORMATS = {"webp": "image/webp", "jpg": "image/jpeg", "png": "image/png"}
ROTATIONS = frozenset({0, 90, 180, 270})
INTERNAL_AUTH_HEADER = "X-Jdhp-Image-Auth"
_PX = re.compile(r"^(\d+),(\d+),(\d+),(\d+)$")
_PCT = re.compile(r"^pct:(\d+(?:\.\d+)?),(\d+(?:\.\d+)?),(\d+(?:\.\d+)?),(\d+(?:\.\d+)?)$")
_SIZE_WH = re.compile(r"^(\d*),(\d*)$")
_SIZE_PCT = re.compile(r"^pct:(\d+(?:\.\d+)?)$")


@dataclasses.dataclass(frozen=True, slots=True)
class ImageInfo:
    width: int
    height: int


@dataclasses.dataclass(frozen=True, slots=True)
class Region:
    x: int
    y: int
    width: int
    height: int


@dataclasses.dataclass(frozen=True, slots=True)
class TileRequest:
    """A validated IIIF request resolved against the source image's dimensions."""

    region: Region
    out_width: int
    out_height: int
    rotation: int
    quality: str
    format: str
    requested_max: bool

    @property
    def media_type(self) -> str:
        return FORMATS[self.format]

    @property
    def pixel_area(self) -> int:
        return self.out_width * self.out_height


def parse_region(text: str, info: ImageInfo) -> Region:
    if text == "full":
        return Region(0, 0, info.width, info.height)
    if text == "square":
        side = min(info.width, info.height)
        return Region((info.width - side) // 2, (info.height - side) // 2, side, side)
    if match := _PX.match(text):
        x, y, w, h = (int(v) for v in match.groups())
    elif match := _PCT.match(text):
        px, py, pw, ph = (float(v) for v in match.groups())
        x = int(info.width * px / 100)
        y = int(info.height * py / 100)
        w = math.ceil(info.width * pw / 100)
        h = math.ceil(info.height * ph / 100)
    else:
        raise TileRequestError
    if w <= 0 or h <= 0 or x >= info.width or y >= info.height:
        raise TileRequestError
    return Region(x, y, min(w, info.width - x), min(h, info.height - y))


def parse_size(text: str, region: Region) -> tuple[int, int, bool]:
    """Output width and height for a size expression, plus whether ``max`` was asked for."""
    if text.startswith("^"):
        raise TileRequestError  # upscaling is never offered
    if text in {"max", "full"}:
        return region.width, region.height, True
    if match := _SIZE_PCT.match(text):
        pct = float(match.group(1))
        if not 0 < pct <= 100:
            raise TileRequestError
        return (
            max(1, round(region.width * pct / 100)),
            max(1, round(region.height * pct / 100)),
            False,
        )
    confined = text.startswith("!")
    body = text[1:] if confined else text
    match = _SIZE_WH.match(body)
    if not match or (not match.group(1) and not match.group(2)):
        raise TileRequestError
    w = int(match.group(1)) if match.group(1) else None
    h = int(match.group(2)) if match.group(2) else None
    ratio = region.height / region.width
    if confined and w is not None and h is not None:
        scale = min(w / region.width, h / region.height)
        w, h = max(1, round(region.width * scale)), max(1, round(region.height * scale))
    elif w is not None and h is None:
        h = max(1, round(w * ratio))
    elif h is not None and w is None:
        w = max(1, round(h / ratio))
    if w is None or h is None:  # pragma: no cover - every branch above sets both
        raise TileRequestError
    if w <= 0 or h <= 0 or w > region.width or h > region.height:
        raise TileRequestError  # never larger than the source region
    return w, h, False


def parse_request(
    *,
    region: str,
    size: str,
    rotation: str,
    quality: str,
    fmt: str,
    info: ImageInfo,
    max_pixels: int,
    allow_max: bool,
) -> TileRequest:
    """Validate every IIIF parameter and enforce the pixel cap (SEC-10)."""
    if quality not in QUALITIES or fmt not in FORMATS:
        raise TileRequestError
    try:
        degrees = int(rotation)
    except ValueError as exc:
        raise TileRequestError from exc
    if degrees not in ROTATIONS:
        raise TileRequestError
    resolved_region = parse_region(region, info)
    width, height, requested_max = parse_size(size, resolved_region)
    if requested_max:
        if not allow_max:
            raise TileTooLargeError
        # ``max`` means the largest size the limits permit (IIIF 3.0 maxArea), never more.
        if width * height > max_pixels:
            scale = math.sqrt(max_pixels / (width * height))
            width, height = max(1, int(width * scale)), max(1, int(height * scale))
    if width * height > max_pixels:
        raise TileTooLargeError
    return TileRequest(
        region=resolved_region,
        out_width=width,
        out_height=height,
        rotation=degrees,
        quality=quality,
        format=fmt,
        requested_max=requested_max,
    )


def info_document(
    *, service_id: str, info: ImageInfo, tile_size: int, max_pixels: int
) -> dict[str, object]:
    """``info.json`` that advertises only what the gateway will serve (SEC-10)."""
    largest = max(info.width, info.height)
    factors: list[int] = []
    factor = 1
    while largest / factor > tile_size / 2 and len(factors) < 8:
        factors.append(factor)
        factor *= 2
    if not factors:
        factors = [1]
    sizes: list[dict[str, int]] = []
    for f in factors:
        w, h = math.ceil(info.width / f), math.ceil(info.height / f)
        if w * h <= max_pixels:
            sizes.append({"width": w, "height": h})
    side = int(math.sqrt(max_pixels))
    return {
        "@context": "http://iiif.io/api/image/3/context.json",
        "id": service_id,
        "type": "ImageService3",
        "protocol": "http://iiif.io/api/image",
        "profile": "level1",
        "width": info.width,
        "height": info.height,
        "maxArea": max_pixels,
        "maxWidth": min(info.width, max(side, tile_size)),
        "maxHeight": min(info.height, max(side, tile_size)),
        "tiles": [{"width": tile_size, "height": tile_size, "scaleFactors": factors}],
        "sizes": sizes,
        "preferredFormats": ["webp"],
        "extraFormats": ["webp"],
        "extraQualities": ["gray"],
        "extraFeatures": [
            "regionByPct",
            "regionByPx",
            "regionSquare",
            "rotationBy90s",
            "sizeByConfinedWh",
            "sizeByH",
            "sizeByPct",
            "sizeByW",
            "sizeByWh",
        ],
    }


class ImageSource(Protocol):
    async def info(self, key: str) -> ImageInfo: ...

    async def tile(self, key: str, request: TileRequest) -> pyvips.Image: ...


def _encode(image: pyvips.Image, fmt: str) -> bytes:
    if fmt == "webp":
        return bytes(image.webpsave_buffer(Q=80, effort=4, strip=True))
    if fmt == "jpg":
        return bytes(image.jpegsave_buffer(Q=85, strip=True, optimize_coding=True))
    return bytes(image.pngsave_buffer(compression=6, strip=True))


def encode(image: pyvips.Image, fmt: str) -> bytes:
    """Serialize a finished tile in the requested format."""
    return _encode(image, fmt)


def _finish(image: pyvips.Image, request: TileRequest) -> pyvips.Image:
    if image.hasalpha():
        image = image.flatten(background=[255, 255, 255])
    if request.quality == "gray":
        image = image.colourspace("b-w")
    if request.rotation:
        image = image.rotate(request.rotation)
    return image


class LibvipsSource:
    """Crops the JPEG 2000 (or pyramidal TIFF) access derivative straight from the bucket."""

    def __init__(self, store: ObjectStore, bucket: str) -> None:
        self._store = store
        self._bucket = bucket

    async def info(self, key: str) -> ImageInfo:
        image = pyvips.Image.new_from_buffer(self._store.get(self._bucket, key), "")
        return ImageInfo(width=image.width, height=image.height)

    async def tile(self, key: str, request: TileRequest) -> pyvips.Image:
        data = self._store.get(self._bucket, key)
        image = pyvips.Image.new_from_buffer(data, "")
        region = request.region
        crop = image.crop(region.x, region.y, region.width, region.height)
        scale = request.out_width / region.width
        if abs(scale - 1.0) > 1e-9:
            crop = crop.resize(scale, vscale=request.out_height / region.height, kernel="lanczos3")
        return _finish(crop, request)


class CantaloupeSource:
    """Asks the image server for the region with the signed internal header (SEC-10, SEC-24)."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if settings.image_internal_key is None:
            msg = "JDHP_IMAGE_INTERNAL_KEY is required for the Cantaloupe image source"
            raise ValueError(msg)
        self._base = str(settings.cantaloupe_url).rstrip("/")
        self._key = settings.image_internal_key.get_secret_value().encode()
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(20.0))

    def _signed_headers(self, path: str) -> dict[str, str]:
        timestamp = str(int(time.time()))
        digest = hmac.new(self._key, f"{timestamp}|{path}".encode(), hashlib.sha256).hexdigest()
        return {INTERNAL_AUTH_HEADER: f"{timestamp}.{digest}"}

    @staticmethod
    def identifier(key: str) -> str:
        return urllib.parse.quote(key, safe="")

    async def _get(self, path: str) -> httpx.Response:
        response = await self._client.get(f"{self._base}{path}", headers=self._signed_headers(path))
        response.raise_for_status()
        return response

    async def info(self, key: str) -> ImageInfo:
        response = await self._get(f"/iiif/3/{self.identifier(key)}/info.json")
        body = response.json()
        return ImageInfo(width=int(body["width"]), height=int(body["height"]))

    async def tile(self, key: str, request: TileRequest) -> pyvips.Image:
        region = request.region
        path = (
            f"/iiif/3/{self.identifier(key)}/{region.x},{region.y},{region.width},{region.height}"
            f"/{request.out_width},{request.out_height}/0/default.png"
        )
        response = await self._get(path)
        image = pyvips.Image.new_from_buffer(response.content, "")
        return _finish(image, request)


def make_image_source(settings: Settings, store: ObjectStore) -> ImageSource:
    if settings.image_source == "libvips":
        return LibvipsSource(store, settings.bucket_access)
    return CantaloupeSource(settings)
