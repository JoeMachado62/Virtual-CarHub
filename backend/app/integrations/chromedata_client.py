from __future__ import annotations

import base64
import hashlib
import hmac
from email.utils import formatdate
from typing import Any
from urllib.parse import quote, urlparse

import httpx

from app.integrations.base_client import ExternalServiceClient, ServicePolicy


def _encode_segment(value: object) -> str:
    return quote(str(value).strip(), safe="")


def _utc_http_date() -> str:
    return formatdate(timeval=None, localtime=False, usegmt=True)


def _build_authtoken(*, api_key: str, api_secret: str, date_value: str) -> str:
    signature_content = f"date: {date_value}"
    signature_digest = hmac.new(
        api_secret.encode("utf-8"),
        msg=signature_content.encode("utf-8"),
        digestmod=hashlib.sha1,
    ).digest()
    signature_base64 = base64.b64encode(signature_digest).decode("ascii")
    encoded_signature = quote(signature_base64, safe="")
    return f'Signature keyId="{api_key}",algorithm="hmac-sha1",signature="{encoded_signature}"'


_HMAC_POLICY = ServicePolicy(max_retries=1, timeout_seconds=15, failure_threshold=5, recovery_seconds=300)


class ChromeDataHmacClient(ExternalServiceClient):
    """Base client for ChromeData services using Tyk HMAC-SHA1 authentication."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str = "",
        api_secret: str = "",
        profile_key: str = "",
        live: bool = False,
        policy: ServicePolicy | None = None,
    ):
        self.live = live
        self.api_key = api_key.strip()
        self.api_secret = api_secret.strip()
        self.profile_key = profile_key.strip()
        super().__init__(
            base_url=base_url,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Accept-Encoding": "gzip",
            },
            policy=policy or _HMAC_POLICY,
        )

    def _headers_for_request(self) -> dict[str, str]:
        headers = super()._headers_for_request()
        if self.api_key and self.api_secret:
            date_value = _utc_http_date()
            headers["Date"] = date_value
            headers["Authtoken"] = _build_authtoken(
                api_key=self.api_key,
                api_secret=self.api_secret,
                date_value=date_value,
            )
        return headers

    def _query_params(self, extra: dict[str, Any] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if self.profile_key:
            params["profileKey"] = self.profile_key
        if extra:
            params.update({key: value for key, value in extra.items() if value not in (None, "")})
        return params


class ChromeDataCvdClient(ChromeDataHmacClient):
    """Client for ChromeData VIN Description (CVD) service."""

    def _request_fallback(
        self,
        method: str,
        candidates: list[tuple[str, dict[str, Any]]],
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for path, params in candidates:
            try:
                response = self._request(method, path, params=params)
                return response if isinstance(response, dict) else {"value": response}
            except httpx.HTTPStatusError as exc:
                last_error = exc
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code not in {404, 405}:
                    raise
        if last_error is not None:
            raise last_error
        return {}

    def get_vin_description(
        self,
        vin: str,
        *,
        locale: str,
        vin_with_all_content: bool = True,
        inc_rgb_hex: bool = True,
        include_alt_model: bool = True,
        include_vehicle_indicator: bool = True,
    ) -> dict[str, Any]:
        if not self.live:
            return {"source": "stub", "result": {}}
        params = self._query_params(
            {
                "vinWithAllContent": str(vin_with_all_content).lower(),
                "incRgbHex": str(inc_rgb_hex).lower(),
                "includeAltModel": str(include_alt_model).lower(),
                "includeVehicleIndicator": str(include_vehicle_indicator).lower(),
            }
        )
        return self._request_fallback(
            "GET",
            [
                (f"/vin/{_encode_segment(vin)}", {**params, "language_Locale": locale}),
                (f"/vindescription/{_encode_segment(locale)}/{_encode_segment(vin)}", params),
                ("/vindescription", {**params, "vin": vin, "language_Locale": locale}),
            ],
        )


class ChromeDataVssClient(ChromeDataHmacClient):
    """Client for ChromeData Vehicle Selector Service (VSS)."""

    def get_years(self, *, locale: str) -> dict[str, Any]:
        if not self.live:
            return {"source": "stub", "result": {}}
        return self._request("GET", "/years", params=self._query_params({"locale": locale}))

    def get_makes(self, *, year: int, locale: str) -> dict[str, Any]:
        if not self.live:
            return {"source": "stub", "result": {}}
        return self._request("GET", "/makes", params=self._query_params({"year": year, "locale": locale}))

    def get_models(self, *, year: int, make_code: str, locale: str) -> dict[str, Any]:
        if not self.live:
            return {"source": "stub", "result": {}}
        return self._request(
            "GET",
            "/models",
            params=self._query_params({"year": year, "makeCode": make_code, "locale": locale}),
        )

    def get_styles(self, *, year: int, make_code: str, model: str, locale: str) -> dict[str, Any]:
        if not self.live:
            return {"source": "stub", "result": {}}
        return self._request(
            "GET",
            "/styles",
            params=self._query_params(
                {
                    "year": year,
                    "makeCode": make_code,
                    "model": model,
                    "locale": locale,
                }
            ),
        )

    def get_style_details(
        self,
        style_id: int,
        *,
        locale: str,
        inc_rgb_hex: bool = True,
        include_alt_model: bool = True,
        include_vehicle_indicator: bool = True,
    ) -> dict[str, Any]:
        if not self.live:
            return {"source": "stub", "result": {}}
        return self._request(
            "GET",
            "/styleDetails",
            params=self._query_params(
                {
                    "styleId": style_id,
                    "locale": locale,
                    "incRgbHex": str(inc_rgb_hex).lower(),
                    "includeAltModel": str(include_alt_model).lower(),
                    "includeVehicleIndicator": str(include_vehicle_indicator).lower(),
                }
            ),
        )


class ChromeDataMediaClient(ExternalServiceClient):
    """Client for Chrome Image Gallery / Chrome Media Server content URLs."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        password: str,
        live: bool = False,
    ):
        self.live = live
        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        super().__init__(
            base_url=base_url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Basic {token}",
            },
            policy=ServicePolicy(max_retries=1, timeout_seconds=15, failure_threshold=5, recovery_seconds=300),
        )

    def _request_json_path(self, path: str) -> Any:
        try:
            return self._request("GET", f"{path}.json")
        except httpx.HTTPStatusError as exc:
            if exc.response is None or exc.response.status_code != 404:
                raise
        return self._request("GET", path)

    def _relative_path(self, path_or_url: str) -> str:
        value = (path_or_url or "").strip()
        if not value:
            return "/"
        if value.startswith("http://") or value.startswith("https://"):
            parsed = urlparse(value)
            path = parsed.path or "/"
            base_parsed = urlparse(self.base_url)
            base_path = base_parsed.path.rstrip("/")
            if base_path and path.startswith(base_path):
                trimmed = path[len(base_path):] or "/"
            else:
                trimmed = path
            return trimmed if trimmed.startswith("/") else f"/{trimmed}"
        return value if value.startswith("/") else f"/{value}"

    def get_resource(self, path_or_url: str) -> dict[str, Any]:
        if not self.live:
            return {"source": "stub"}
        data = self._request_json_path(self._relative_path(path_or_url))
        return data if isinstance(data, dict) else {"value": data}

    def get_style_media(self, style_id: int) -> dict[str, Any]:
        if not self.live:
            return {"source": "stub", "styleMedia": {}}
        data = self.get_resource(f"/style/{_encode_segment(style_id)}")
        return data if isinstance(data, dict) else {"styleMedia": data}

    def get_vehicle_media(
        self,
        *,
        country: str,
        year: int,
        division: str,
        model: str,
        body_type: str | None = None,
    ) -> dict[str, Any]:
        if not self.live:
            return {"source": "stub", "modelMedia": {}}
        segments = [
            _encode_segment(country),
            _encode_segment(year),
            _encode_segment(division),
            _encode_segment(model),
        ]
        if body_type:
            segments.append(_encode_segment(body_type))
        data = self.get_resource("/" + "/".join(segments))
        return data if isinstance(data, dict) else {"modelMedia": data}
