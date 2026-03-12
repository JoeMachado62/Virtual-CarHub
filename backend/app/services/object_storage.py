from __future__ import annotations

from urllib.parse import quote

from app.core.config import settings


def resolve_storage_url(storage_key: str | None) -> str | None:
    if storage_key is None:
        return None

    key = str(storage_key).strip()
    if not key:
        return None

    if key.startswith(("http://", "https://")):
        return key

    if key.startswith("s3://"):
        bucket, object_key = _split_s3_uri(key)
        if not bucket or not object_key:
            return key
        return _public_s3_url(bucket, object_key)

    normalized_key = _normalize_object_key(key)
    if not normalized_key:
        return None

    if settings.object_storage_public_base_url:
        base = settings.object_storage_public_base_url.rstrip("/")
        return f"{base}/{quote(normalized_key, safe='/')}"

    if settings.aws_cloudfront_domain:
        domain = settings.aws_cloudfront_domain.strip().rstrip("/")
        if domain:
            if not domain.startswith(("http://", "https://")):
                domain = f"https://{domain}"
            return f"{domain}/{quote(normalized_key, safe='/')}"

    if settings.s3_assets_bucket:
        return _public_s3_url(settings.s3_assets_bucket, normalized_key)

    return key


def _split_s3_uri(uri: str) -> tuple[str | None, str | None]:
    if not uri.startswith("s3://"):
        return None, None

    value = uri[5:]
    if "/" not in value:
        return value, ""

    bucket, key = value.split("/", 1)
    return bucket.strip(), _normalize_object_key(key)


def _normalize_object_key(value: str) -> str:
    return value.lstrip("/")


def _public_s3_url(bucket: str, key: str) -> str:
    endpoint = settings.aws_s3_endpoint_url.strip().rstrip("/")
    if endpoint:
        return f"{endpoint}/{bucket}/{quote(key, safe='/')}"

    region = settings.aws_region.strip() or "us-east-1"
    if region == "us-east-1":
        return f"https://{bucket}.s3.amazonaws.com/{quote(key, safe='/')}"
    return f"https://{bucket}.s3.{region}.amazonaws.com/{quote(key, safe='/')}"
