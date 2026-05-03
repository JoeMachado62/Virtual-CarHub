from __future__ import annotations

import pytest

from app.core.config import settings
from app.services.s3_service import (
    S3ConfigurationError,
    cache_remote_image,
    normalize_s3_key,
    upload_image_bytes,
)


class FakeS3Client:
    def __init__(self) -> None:
        self.put_calls: list[dict] = []

    def put_object(self, **kwargs):
        self.put_calls.append(kwargs)
        return {"ETag": '"fake-etag"'}


class FakeHttpResponse:
    def __init__(
        self,
        *,
        body: bytes,
        content_type: str,
        url: str = "https://images.example/car.jpg",
    ) -> None:
        self.body = body
        self.headers = {"content-type": content_type}
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        return None

    def iter_bytes(self):
        yield self.body

    def raise_for_status(self) -> None:
        return None


class FakeHttpClient:
    def __init__(self, response: FakeHttpResponse) -> None:
        self.response = response

    def stream(self, method: str, url: str, follow_redirects: bool = True) -> FakeHttpResponse:
        self.request_method = method
        self.request_url = url
        self.follow_redirects = follow_redirects
        return self.response


def test_upload_image_bytes_uses_assets_bucket_and_resolves_public_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_s3 = FakeS3Client()
    monkeypatch.setattr(settings, "object_storage_provider", "s3")
    monkeypatch.setattr(settings, "s3_assets_bucket", "vch-assets")
    monkeypatch.setattr(settings, "object_storage_public_base_url", "https://assets.example.com")
    monkeypatch.setattr(settings, "aws_cloudfront_domain", "")

    result = upload_image_bytes(
        key="/source-cache/VIN123/marketcheck/001.jpg",
        body=b"\xff\xd8\xffimage-bytes",
        content_type="image/jpeg",
        client=fake_s3,
    )

    assert result.bucket == "vch-assets"
    assert result.key == "source-cache/VIN123/marketcheck/001.jpg"
    assert result.storage_key == "source-cache/VIN123/marketcheck/001.jpg"
    assert result.url == "https://assets.example.com/source-cache/VIN123/marketcheck/001.jpg"
    assert result.etag == "fake-etag"
    assert fake_s3.put_calls[0]["ServerSideEncryption"] == "AES256"
    assert fake_s3.put_calls[0]["Metadata"]["sha256"] == result.sha256


def test_upload_image_bytes_requires_s3_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "object_storage_provider", "none")
    monkeypatch.setattr(settings, "s3_assets_bucket", "vch-assets")

    with pytest.raises(S3ConfigurationError):
        upload_image_bytes(
            key="source-cache/VIN123/marketcheck/001.jpg",
            body=b"\xff\xd8\xffimage-bytes",
            content_type="image/jpeg",
            client=FakeS3Client(),
        )


def test_normalize_s3_key_rejects_relative_segments() -> None:
    with pytest.raises(ValueError):
        normalize_s3_key("source-cache/../secret.jpg")


def test_cache_remote_image_sniffs_content_type_and_hashes_source_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_s3 = FakeS3Client()
    fake_http = FakeHttpClient(
        FakeHttpResponse(
            body=b"\x89PNG\r\n\x1a\nimage-bytes",
            content_type="application/octet-stream",
        )
    )
    monkeypatch.setattr(settings, "object_storage_provider", "s3")
    monkeypatch.setattr(settings, "s3_assets_bucket", "vch-assets")
    monkeypatch.setattr(settings, "object_storage_public_base_url", "")
    monkeypatch.setattr(settings, "aws_cloudfront_domain", "cdn.example.com")

    result = cache_remote_image(
        source_url="https://images.example/car.jpg?token=secret",
        key="source-cache/VIN123/marketcheck/001.png",
        http_client=fake_http,
        s3_client=fake_s3,
    )

    assert result.content_type == "image/png"
    assert result.url == "https://cdn.example.com/source-cache/VIN123/marketcheck/001.png"
    assert "source_url_sha256" in fake_s3.put_calls[0]["Metadata"]
    assert "token=secret" not in str(fake_s3.put_calls[0]["Metadata"])
