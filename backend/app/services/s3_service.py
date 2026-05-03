from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from ipaddress import ip_address
from typing import Any
from urllib.parse import urlsplit

import httpx

from app.core.config import settings
from app.services.object_storage import resolve_storage_url


DEFAULT_IMAGE_CACHE_CONTROL = "public, max-age=31536000, immutable"
DEFAULT_MAX_IMAGE_BYTES = 15 * 1024 * 1024
ALLOWED_IMAGE_CONTENT_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/avif": ".avif",
}


class S3ServiceError(RuntimeError):
    """Base error for object-storage upload failures."""


class S3ConfigurationError(S3ServiceError):
    """Raised when S3 uploads are requested without S3 settings."""


class S3UploadError(S3ServiceError):
    """Raised when an object upload fails."""


class RemoteImageFetchError(S3ServiceError):
    """Raised when a remote image cannot be safely fetched."""


@dataclass(frozen=True, slots=True)
class S3UploadResult:
    bucket: str
    key: str
    storage_key: str
    url: str | None
    content_type: str
    sha256: str
    size_bytes: int
    etag: str | None = None


@dataclass(frozen=True, slots=True)
class DownloadedImage:
    body: bytes
    content_type: str


def object_storage_uploads_enabled(bucket: str | None = None) -> bool:
    return settings.object_storage_provider == "s3" and bool(_configured_bucket(bucket))


def upload_image_bytes(
    *,
    key: str,
    body: bytes | bytearray | memoryview,
    content_type: str,
    bucket: str | None = None,
    cache_control: str = DEFAULT_IMAGE_CACHE_CONTROL,
    metadata: dict[str, str] | None = None,
    client: Any | None = None,
) -> S3UploadResult:
    data = bytes(body)
    if not data:
        raise ValueError("Cannot upload an empty image body")

    normalized_key = normalize_s3_key(key)
    bucket_name = _require_bucket(bucket)
    normalized_content_type = normalize_image_content_type(content_type, body=data)
    digest = sha256(data).hexdigest()
    object_metadata = {"sha256": digest}
    if metadata:
        object_metadata.update({str(k): str(v) for k, v in metadata.items() if v is not None})

    put_kwargs: dict[str, Any] = {
        "Bucket": bucket_name,
        "Key": normalized_key,
        "Body": data,
        "ContentType": normalized_content_type,
        "CacheControl": cache_control,
        "Metadata": object_metadata,
        "ServerSideEncryption": "AES256",
    }

    try:
        response = (client or _s3_client()).put_object(**put_kwargs)
    except Exception as exc:  # pragma: no cover - concrete SDK errors vary by provider
        target = f"s3://{bucket_name}/{normalized_key}"
        raise S3UploadError(f"Failed to upload image to {target}") from exc

    storage_key = _storage_key_for_bucket(bucket_name, normalized_key)
    etag = str(response.get("ETag", "")).strip('"') if isinstance(response, dict) else None
    return S3UploadResult(
        bucket=bucket_name,
        key=normalized_key,
        storage_key=storage_key,
        url=resolve_storage_url(storage_key),
        content_type=normalized_content_type,
        sha256=digest,
        size_bytes=len(data),
        etag=etag or None,
    )


def cache_remote_image(
    *,
    source_url: str,
    key: str,
    bucket: str | None = None,
    cache_control: str = DEFAULT_IMAGE_CACHE_CONTROL,
    max_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
    timeout_seconds: float = 10.0,
    http_client: httpx.Client | None = None,
    s3_client: Any | None = None,
) -> S3UploadResult:
    image = download_remote_image(
        source_url,
        max_bytes=max_bytes,
        timeout_seconds=timeout_seconds,
        http_client=http_client,
    )
    return upload_image_bytes(
        key=key,
        body=image.body,
        content_type=image.content_type,
        bucket=bucket,
        cache_control=cache_control,
        metadata={"source_url_sha256": sha256(source_url.encode("utf-8")).hexdigest()},
        client=s3_client,
    )


def download_remote_image(
    source_url: str,
    *,
    max_bytes: int = DEFAULT_MAX_IMAGE_BYTES,
    timeout_seconds: float = 10.0,
    http_client: httpx.Client | None = None,
) -> DownloadedImage:
    safe_url = _validate_remote_url(source_url)
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout_seconds, follow_redirects=True)
    try:
        with client.stream("GET", safe_url, follow_redirects=True) as response:
            response.raise_for_status()
            final_url = str(response.url)
            _validate_remote_url(final_url)
            chunks: list[bytes] = []
            total_bytes = 0
            for chunk in response.iter_bytes():
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise RemoteImageFetchError(f"Remote image exceeds {max_bytes} bytes")
                chunks.append(chunk)
            body = b"".join(chunks)
            header_content_type = response.headers.get("content-type", "")
    except httpx.HTTPError as exc:
        raise RemoteImageFetchError(f"Failed to fetch remote image: {safe_url}") from exc
    finally:
        if owns_client:
            client.close()

    try:
        content_type = normalize_image_content_type(header_content_type, body=body)
    except ValueError as exc:
        raise RemoteImageFetchError("Remote image has an unsupported content type") from exc
    return DownloadedImage(body=body, content_type=content_type)


def normalize_s3_key(key: str) -> str:
    normalized = str(key).strip().replace("\\", "/").lstrip("/")
    if not normalized:
        raise ValueError("S3 object key is required")
    if any(ord(char) < 32 for char in normalized):
        raise ValueError("S3 object key contains control characters")
    if any(part in {"", ".", ".."} for part in normalized.split("/")):
        raise ValueError("S3 object key must not contain empty or relative path segments")
    return normalized


def normalize_image_content_type(content_type: str, *, body: bytes | None = None) -> str:
    media_type = str(content_type).split(";", 1)[0].strip().lower()
    if media_type in ALLOWED_IMAGE_CONTENT_TYPES:
        return media_type

    sniffed = _sniff_image_content_type(body or b"")
    if sniffed:
        return sniffed

    raise ValueError(f"Unsupported image content type: {content_type or 'unknown'}")


def _configured_bucket(bucket: str | None = None) -> str:
    return (bucket or settings.s3_assets_bucket or "").strip()


def _require_bucket(bucket: str | None = None) -> str:
    if settings.object_storage_provider != "s3":
        raise S3ConfigurationError("OBJECT_STORAGE_PROVIDER must be set to 's3' to upload images")

    bucket_name = _configured_bucket(bucket)
    if not bucket_name:
        raise S3ConfigurationError("S3_ASSETS_BUCKET is required to upload images")
    return bucket_name


def _storage_key_for_bucket(bucket: str, key: str) -> str:
    if bucket == _configured_bucket():
        return key
    return f"s3://{bucket}/{key}"


def _s3_client() -> Any:
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover - guarded by requirements
        raise S3ConfigurationError("boto3 is required for S3 uploads") from exc

    endpoint_url = settings.aws_s3_endpoint_url.strip() or None
    region_name = settings.aws_region.strip() or None
    return boto3.client("s3", region_name=region_name, endpoint_url=endpoint_url)


def _validate_remote_url(url: str) -> str:
    parsed = urlsplit(str(url).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise RemoteImageFetchError("Remote image URL must be http(s)")

    host = (parsed.hostname or "").strip().lower()
    if not host or host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".localhost"):
        raise RemoteImageFetchError("Remote image URL host is not allowed")
    try:
        address = ip_address(host)
    except ValueError:
        address = None
    if address and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise RemoteImageFetchError("Remote image URL host is not allowed")

    return parsed.geturl()


def _sniff_image_content_type(body: bytes) -> str | None:
    if body.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if body.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "image/webp"
    if len(body) >= 12 and body[4:8] == b"ftyp" and body[8:12] in {b"avif", b"avis"}:
        return "image/avif"
    return None
