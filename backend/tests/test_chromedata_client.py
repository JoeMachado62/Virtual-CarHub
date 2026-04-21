import base64
import hashlib
import hmac
from urllib.parse import quote

import httpx
import pytest

from app.integrations.chromedata_client import (
    ChromeDataCvdClient,
    ChromeDataVssClient,
)
from app.integrations import chromedata_client as chromedata_client_module


# ---------------------------------------------------------------------------
# Shared HMAC auth (tested via CVD client; VSS inherits the same base)
# ---------------------------------------------------------------------------


def test_headers_for_request_include_signed_authtoken(monkeypatch) -> None:
    fixed_date = "Thu, 15 May 2025 17:40:21 GMT"
    api_key = "test-key"
    api_secret = "test-secret="
    monkeypatch.setattr(chromedata_client_module, "_utc_http_date", lambda: fixed_date)

    client = ChromeDataCvdClient(
        base_url="https://example.com",
        api_key=api_key,
        api_secret=api_secret,
        profile_key="profile-123",
        live=True,
    )

    headers = client._headers_for_request()
    signature = hmac.new(
        api_secret.encode("utf-8"),
        msg=f"date: {fixed_date}".encode("utf-8"),
        digestmod=hashlib.sha1,
    ).digest()
    expected_signature = quote(base64.b64encode(signature).decode("ascii"), safe="")

    assert headers["Accept"] == "application/json"
    assert headers["Content-Type"] == "application/json"
    assert headers["Accept-Encoding"] == "gzip"
    assert headers["Date"] == fixed_date
    assert headers["Authtoken"] == (
        f'Signature keyId="{api_key}",algorithm="hmac-sha1",signature="{expected_signature}"'
    )


def test_pdf_sample_signature(monkeypatch) -> None:
    """Verify the HMAC-SHA1 implementation matches the known-good sample from
    the Tyk Shared Secret Security Protocol PDF."""
    fixed_date = "Thu, 15 May 2025 17:40:21 GMT"
    sample_key = (
        "eyJvcmciOiI2NDI0YTEwNjY2NDU4MDAwMDFmMjk5ODAiLCJpZCI6Ijk3Y2Q0NmE0"
        "ZmI1NTQ4Yjk5YzIxYmUxMzgzODgwMDg0IiwiaCI6Im11cm11cjEyOCJ9"
    )
    sample_secret = "ZDRjM2JjMzYwZDdkNGQ3MjgwNWE4N2Q5NTMyOGYxOGE="
    expected_encoded_sig = "nY9NLuyne8IGbo4KHTcIj9DRpi8%3D"

    monkeypatch.setattr(chromedata_client_module, "_utc_http_date", lambda: fixed_date)

    client = ChromeDataCvdClient(
        base_url="https://example.com",
        api_key=sample_key,
        api_secret=sample_secret,
        live=True,
    )
    headers = client._headers_for_request()
    authtoken = headers["Authtoken"]
    actual_sig = authtoken.split('signature="')[1].rstrip('"')
    assert actual_sig == expected_encoded_sig


# ---------------------------------------------------------------------------
# CVD client
# ---------------------------------------------------------------------------


def test_get_vin_description_prefers_guide_endpoint(monkeypatch) -> None:
    client = ChromeDataCvdClient(
        base_url="https://example.com",
        api_key="test-key",
        api_secret="test-secret=",
        profile_key="profile-123",
        live=True,
    )
    calls: list[tuple[str, str, dict]] = []

    def fake_request(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs))
        return {"result": {"vinSubmitted": "1FD8W3H69LEC38010"}}

    monkeypatch.setattr(client, "_request", fake_request)

    response = client.get_vin_description("1FD8W3H69LEC38010", locale="en_US")

    assert response["result"]["vinSubmitted"] == "1FD8W3H69LEC38010"
    assert calls == [
        (
            "GET",
            "/vindescription/en_US/1FD8W3H69LEC38010",
            {
                "params": {
                    "profileKey": "profile-123",
                    "vinWithAllContent": "true",
                    "incRgbHex": "true",
                    "includeAltModel": "true",
                    "includeVehicleIndicator": "true",
                }
            },
        )
    ]


def test_get_vin_description_falls_back_when_guide_path_404(monkeypatch) -> None:
    client = ChromeDataCvdClient(
        base_url="https://example.com",
        api_key="test-key",
        api_secret="test-secret=",
        live=True,
    )
    calls: list[tuple[str, str, dict]] = []

    def fake_request(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs))
        if len(calls) == 1:
            request = httpx.Request(method, f"https://example.com{path}")
            response = httpx.Response(404, request=request)
            raise httpx.HTTPStatusError("not found", request=request, response=response)
        return {"result": {"ok": True}}

    monkeypatch.setattr(client, "_request", fake_request)

    response = client.get_vin_description("1FD8W3H69LEC38010", locale="en_US")

    assert response["result"]["ok"] is True
    assert [path for _method, path, _kwargs in calls] == [
        "/vindescription/en_US/1FD8W3H69LEC38010",
        "/vindescription",
    ]


def test_cvd_client_does_not_have_vss_methods() -> None:
    """Regression guard: VSS methods belong on ChromeDataVssClient, not CVD."""
    for method_name in ("get_years", "get_makes", "get_models", "get_styles", "get_style_details"):
        assert not hasattr(ChromeDataCvdClient, method_name), (
            f"ChromeDataCvdClient should not have VSS method '{method_name}'"
        )


# ---------------------------------------------------------------------------
# VSS client
# ---------------------------------------------------------------------------


def test_vss_client_headers_include_signed_authtoken(monkeypatch) -> None:
    """VSS client inherits HMAC auth from the shared base class."""
    fixed_date = "Thu, 15 May 2025 17:40:21 GMT"
    api_key = "vss-key"
    api_secret = "vss-secret="
    monkeypatch.setattr(chromedata_client_module, "_utc_http_date", lambda: fixed_date)

    client = ChromeDataVssClient(
        base_url="https://vss-api.jdpower.com/VSS/v1.0",
        api_key=api_key,
        api_secret=api_secret,
        live=True,
    )

    headers = client._headers_for_request()
    assert "Date" in headers
    assert "Authtoken" in headers
    assert headers["Date"] == fixed_date
    assert f'keyId="{api_key}"' in headers["Authtoken"]


def test_vss_get_styles_sends_correct_params(monkeypatch) -> None:
    client = ChromeDataVssClient(
        base_url="https://vss-api.jdpower.com/VSS/v1.0",
        api_key="key",
        api_secret="secret",
        profile_key="prof",
        live=True,
    )
    calls: list[tuple[str, str, dict]] = []

    def fake_request(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs))
        return {"styles": []}

    monkeypatch.setattr(client, "_request", fake_request)

    client.get_styles(year=2024, make_code="Ford", model="F-150", locale="en_US")

    assert len(calls) == 1
    method, path, kwargs = calls[0]
    assert method == "GET"
    assert path == "/styles"
    assert kwargs["params"] == {
        "profileKey": "prof",
        "year": 2024,
        "makeCode": "Ford",
        "model": "F-150",
        "locale": "en_US",
    }


def test_vss_get_style_details_sends_correct_params(monkeypatch) -> None:
    client = ChromeDataVssClient(
        base_url="https://vss-api.jdpower.com/VSS/v1.0",
        api_key="key",
        api_secret="secret",
        live=True,
    )
    calls: list[tuple[str, str, dict]] = []

    def fake_request(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs))
        return {"result": {}}

    monkeypatch.setattr(client, "_request", fake_request)

    client.get_style_details(403565, locale="en_US")

    assert len(calls) == 1
    method, path, kwargs = calls[0]
    assert method == "GET"
    assert path == "/styleDetails"
    assert kwargs["params"]["styleId"] == 403565
    assert kwargs["params"]["locale"] == "en_US"


def test_vss_stub_mode_returns_stub() -> None:
    client = ChromeDataVssClient(
        base_url="https://vss-api.jdpower.com/VSS/v1.0",
        api_key="key",
        api_secret="secret",
        live=False,
    )
    assert client.get_years(locale="en_US") == {"source": "stub", "result": {}}
    assert client.get_styles(year=2024, make_code="Ford", model="F-150", locale="en_US") == {
        "source": "stub",
        "result": {},
    }
