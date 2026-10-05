"""SHA-256 fixity: computed at ingest, recorded in the package, verified quarterly."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ChecksumEntry:
    sha256: str
    path: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_stream(chunks: Iterable[bytes]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()


def format_manifest(entries: Iterable[ChecksumEntry]) -> str:
    """The ``sha256sum`` format: hash, two spaces, path, one entry per line."""
    return "".join(f"{entry.sha256}  {entry.path}\n" for entry in entries)


def parse_manifest(text: str) -> Iterator[ChecksumEntry]:
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        digest, _, path = line.partition("  ")
        if len(digest) != 64 or not path:
            msg = f"malformed checksum line: {raw!r}"
            raise ValueError(msg)
        yield ChecksumEntry(sha256=digest.lower(), path=path)
