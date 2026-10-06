"""Object storage for proof photographs.

S3-compatible, so the same code runs against Hetzner Object Storage, MinIO or
AWS — only the endpoint changes.

Uploads are proxied through the API rather than done with a presigned URL
straight from the browser. That costs a little bandwidth but avoids configuring
CORS on the bucket, and it means a driver's phone only ever talks to one host,
which matters when it is on a weak connection in an industrial estate.
"""

from __future__ import annotations

import mimetypes
import secrets
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

# Only what a phone camera or a scanner actually produces.
ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "application/pdf": ".pdf",
}

MAX_BYTES = 12 * 1024 * 1024  # a phone photo, not a video


class StorageError(RuntimeError):
    """Storage is not configured, or the object store refused the upload."""


@dataclass(frozen=True)
class StoredFile:
    key: str
    url: str
    content_type: str
    size: int


@lru_cache
def _client():
    if not (settings.s3_access_key and settings.s3_secret_key):
        raise StorageError(
            "Object storage is not configured. Set S3_ENDPOINT_URL, S3_ACCESS_KEY "
            "and S3_SECRET_KEY."
        )
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        # Hetzner and MinIO both want path-style addressing.
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


def is_configured() -> bool:
    return bool(settings.s3_access_key and settings.s3_secret_key)


def build_key(kind: str, filename: str | None, content_type: str) -> str:
    """Date-partitioned so a bucket listing stays navigable after a year of
    deliveries, and random so two drivers photographing at the same second
    cannot collide."""
    ext = ALLOWED_TYPES.get(content_type) or (
        mimetypes.guess_extension(content_type) if content_type else None
    ) or ".bin"
    today = date.today()
    return f"{kind}/{today:%Y/%m/%d}/{secrets.token_urlsafe(12)}{ext}"


def public_url(key: str) -> str:
    """Where the stored object can be read back.

    `S3_PUBLIC_BASE_URL` covers the common case of a bucket fronted by a CDN or
    a custom domain; otherwise the endpoint and bucket are used directly.
    """
    base = (settings.s3_public_base_url or "").rstrip("/")
    if base:
        return f"{base}/{key}"
    endpoint = (settings.s3_endpoint_url or "").rstrip("/")
    return f"{endpoint}/{settings.s3_bucket}/{key}"


def put_object(data: bytes, key: str, content_type: str) -> StoredFile:
    try:
        _client().put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            # Proof photographs are opened from a customer's tracking link, so
            # they have to be readable without a signed request.
            ACL="public-read",
        )
    except (BotoCoreError, ClientError) as exc:
        raise StorageError(f"Upload failed: {exc}") from exc

    return StoredFile(
        key=key,
        url=public_url(key),
        content_type=content_type,
        size=len(data),
    )


def ensure_bucket() -> None:
    """Create the bucket if it is missing. Safe to call repeatedly."""
    client = _client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket)
    except ClientError:
        try:
            client.create_bucket(Bucket=settings.s3_bucket)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError(f"Could not create bucket {settings.s3_bucket}: {exc}") from exc
