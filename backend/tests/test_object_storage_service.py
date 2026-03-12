from contextlib import contextmanager

from app.core.config import settings
from app.services.object_storage import resolve_storage_url


@contextmanager
def _override_settings(**kwargs):
    original = {key: getattr(settings, key) for key in kwargs}
    try:
        for key, value in kwargs.items():
            setattr(settings, key, value)
        yield
    finally:
        for key, value in original.items():
            setattr(settings, key, value)


def test_resolve_storage_url_passthrough_http() -> None:
    assert resolve_storage_url("https://cdn.example.com/a/b.jpg") == "https://cdn.example.com/a/b.jpg"


def test_resolve_storage_url_with_public_base() -> None:
    with _override_settings(
        object_storage_public_base_url="https://assets.virtualcarhub.com",
        aws_cloudfront_domain="",
        s3_assets_bucket="",
    ):
        assert (
            resolve_storage_url("inventory/2026/abc 123.jpg")
            == "https://assets.virtualcarhub.com/inventory/2026/abc%20123.jpg"
        )


def test_resolve_storage_url_with_cloudfront_fallback() -> None:
    with _override_settings(
        object_storage_public_base_url="",
        aws_cloudfront_domain="d111111abcdef8.cloudfront.net",
        s3_assets_bucket="",
    ):
        assert (
            resolve_storage_url("images/vehicle.webp")
            == "https://d111111abcdef8.cloudfront.net/images/vehicle.webp"
        )


def test_resolve_storage_url_with_bucket_fallback_and_region() -> None:
    with _override_settings(
        object_storage_public_base_url="",
        aws_cloudfront_domain="",
        s3_assets_bucket="vch-assets",
        aws_region="us-west-2",
        aws_s3_endpoint_url="",
    ):
        assert (
            resolve_storage_url("media/vin/photo.jpg")
            == "https://vch-assets.s3.us-west-2.amazonaws.com/media/vin/photo.jpg"
        )


def test_resolve_storage_url_s3_uri_and_custom_endpoint() -> None:
    with _override_settings(
        aws_s3_endpoint_url="https://nyc3.digitaloceanspaces.com",
        aws_region="us-east-1",
    ):
        assert (
            resolve_storage_url("s3://vch-assets/a/b/c.png")
            == "https://nyc3.digitaloceanspaces.com/vch-assets/a/b/c.png"
        )
