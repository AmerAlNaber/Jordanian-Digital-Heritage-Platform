"""METS skeleton round trip and sha256sum-style manifests (preservation rules)."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import pytest

from jdhp_metadata import checksums, mets


def test_mets_round_trip() -> None:
    created = dt.datetime(2026, 10, 4, 12, 0, tzinfo=dt.UTC)
    package = mets.MetsPackage(
        work_public_id="w8abc",
        digital_object_id="do-1",
        created=created,
        title="أخبار بلدة سُميرة",
        files=(
            mets.MetsFile(
                seq=1, key="preservation/w/do/master/1.tif", sha256="a" * 64, size=100, label="غلاف"
            ),
            mets.MetsFile(seq=2, key="preservation/w/do/master/2.tif", sha256="b" * 64, size=200),
        ),
    )
    xml = mets.build_mets(package)
    parsed = mets.parse_mets(xml)
    assert parsed.work_public_id == "w8abc"
    assert parsed.digital_object_id == "do-1"
    assert parsed.created == created
    assert [f.seq for f in parsed.files] == [1, 2]
    assert parsed.files[0].label == "غلاف"
    assert parsed.files[1].sha256 == "b" * 64
    assert parsed.title == "أخبار بلدة سُميرة"


def test_checksum_manifest_round_trip(tmp_path: Path) -> None:
    file = tmp_path / "0001.tif"
    file.write_bytes(b"not really a tiff")
    digest = checksums.sha256_file(file)
    assert digest == checksums.sha256_bytes(b"not really a tiff")
    assert digest == checksums.sha256_stream([b"not really", b" a tiff"])
    manifest = checksums.format_manifest([checksums.ChecksumEntry(digest, "master/0001.tif")])
    assert manifest == f"{digest}  master/0001.tif\n"
    assert list(checksums.parse_manifest(manifest + "# comment\n\n")) == [
        checksums.ChecksumEntry(digest, "master/0001.tif")
    ]
    with pytest.raises(ValueError, match="malformed"):
        list(checksums.parse_manifest("abc  file\n"))
