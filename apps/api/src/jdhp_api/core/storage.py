"""S3-compatible object storage with one client per credential.

The API holds a credential that can read the access bucket and write uploads and exports.
Only the ingest worker holds the credential that writes the preservation bucket (B7 in the
threat model). Keys are built from validated parts, never from request strings (SEC-17).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from jdhp_api.core.config import Settings


@dataclass(frozen=True, slots=True)
class StoredObject:
    key: str
    size: int
    etag: str


class ObjectStore:
    def __init__(
        self,
        *,
        endpoint_url: str | None,
        region: str,
        access_key: str,
        secret_key: str,
        force_path_style: bool = True,
    ) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            region_name=region,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=BotoConfig(
                s3={"addressing_style": "path" if force_path_style else "auto"},
                retries={"max_attempts": 3, "mode": "standard"},
                signature_version="s3v4",
            ),
        )

    @property
    def client(self) -> Any:
        return self._client

    def put(
        self,
        bucket: str,
        key: str,
        data: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> StoredObject:
        response = self._client.put_object(
            Bucket=bucket, Key=key, Body=data, ContentType=content_type
        )
        return StoredObject(key=key, size=len(data), etag=str(response.get("ETag", "")).strip('"'))

    def get(self, bucket: str, key: str) -> bytes:
        response = self._client.get_object(Bucket=bucket, Key=key)
        return bytes(response["Body"].read())

    def head(self, bucket: str, key: str) -> StoredObject | None:
        try:
            response = self._client.head_object(Bucket=bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise
        return StoredObject(
            key=key,
            size=int(response["ContentLength"]),
            etag=str(response.get("ETag", "")).strip('"'),
        )

    def exists(self, bucket: str, key: str) -> bool:
        return self.head(bucket, key) is not None

    def delete(self, bucket: str, key: str) -> None:
        self._client.delete_object(Bucket=bucket, Key=key)

    def list(self, bucket: str, prefix: str) -> Iterator[StoredObject]:
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
            for item in page.get("Contents", []):
                yield StoredObject(
                    key=item["Key"],
                    size=int(item["Size"]),
                    etag=str(item.get("ETag", "")).strip('"'),
                )

    def presigned_get(self, bucket: str, key: str, *, expires_seconds: int) -> str:
        url: str = self._client.generate_presigned_url(
            "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_seconds
        )
        return url

    def ensure_bucket(self, bucket: str, *, object_lock: bool = False) -> None:
        """Create a bucket if it does not exist. Infrastructure does this in deployments."""
        try:
            self._client.head_bucket(Bucket=bucket)
            return
        except ClientError:
            pass
        kwargs: dict[str, Any] = {"Bucket": bucket}
        if object_lock:
            kwargs["ObjectLockEnabledForBucket"] = True
        self._client.create_bucket(**kwargs)


def app_store(settings: Settings) -> ObjectStore:
    return ObjectStore(
        endpoint_url=str(settings.s3_endpoint_url) if settings.s3_endpoint_url else None,
        region=settings.s3_region,
        access_key=settings.s3_access_key.get_secret_value(),
        secret_key=settings.s3_secret_key.get_secret_value(),
        force_path_style=settings.s3_force_path_style,
    )


def master_key(work_id: uuid.UUID, digital_object_id: uuid.UUID, seq: int) -> str:
    return f"{work_id}/{digital_object_id}/master/{seq:04d}.tif"


def mets_key(work_id: uuid.UUID, digital_object_id: uuid.UUID) -> str:
    return f"{work_id}/{digital_object_id}/mets.xml"


def checksums_key(work_id: uuid.UUID, digital_object_id: uuid.UUID) -> str:
    return f"{work_id}/{digital_object_id}/checksums.sha256"


def derivative_key(work_id: uuid.UUID, digital_object_id: uuid.UUID, seq: int, fmt: str) -> str:
    folder, ext = ("jp2", "jp2") if fmt == "jp2" else ("ptif", "tif")
    return f"{work_id}/{digital_object_id}/{folder}/{seq:04d}.{ext}"


def thumb_key(work_id: uuid.UUID, digital_object_id: uuid.UUID, seq: int) -> str:
    return f"{work_id}/{digital_object_id}/thumb/{seq:04d}.webp"


def sample_key(work_id: uuid.UUID, digital_object_id: uuid.UUID, seq: int) -> str:
    return f"{work_id}/{digital_object_id}/sample/{seq:04d}.webp"


def alto_key(work_id: uuid.UUID, digital_object_id: uuid.UUID, seq: int) -> str:
    return f"{work_id}/{digital_object_id}/alto/{seq:04d}.xml"


def offsets_key(work_id: uuid.UUID, digital_object_id: uuid.UUID, seq: int) -> str:
    return f"{work_id}/{digital_object_id}/alto/{seq:04d}.offsets.json"
