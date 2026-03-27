from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.integrations.base_client import ExternalServiceClient, ServicePolicy

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EvoxColor:
    color_code: str
    color_title: str
    color_simpletitle: str


class EvoxClient(ExternalServiceClient):
    """Client for the EVOX Images Automotive Image Library API.

    Auth: api_key query param for GET requests, x-api-key header for POST.
    Docs: https://api.evoximages.com
    """

    def __init__(
        self,
        api_key: str,
        *,
        api_base_url: str = "https://api.evoximages.com/api/v1",
        live: bool = False,
    ):
        self.live = live
        self.api_key = api_key
        super().__init__(
            base_url=api_base_url,
            headers={"Accept": "application/json"},
            policy=ServicePolicy(max_retries=2, timeout_seconds=15, failure_threshold=5, recovery_seconds=300),
        )

    def _get_params(self, extra: dict | None = None) -> dict:
        """Build GET query params with api_key."""
        params: dict[str, Any] = {"api_key": self.api_key}
        if extra:
            params.update(extra)
        return params

    def _post_headers(self) -> dict[str, str]:
        """Build POST headers with x-api-key auth."""
        return {**self.headers, "x-api-key": self.api_key, "Content-Type": "application/json"}

    # ---- Vehicle image queries ----

    def get_vehicle_images(
        self,
        vifid: int,
        product_id: int,
        product_type_id: int,
        *,
        color_code: str | None = None,
        webp: str = "true",
    ) -> dict:
        """GET a single vehicle image by VIFID + product type.

        URL: /vehicles/{VIFID}/products/{ProductID}/{ProductTypeID}
        """
        if not self.live:
            return {"source": "stub", "vifid": vifid}
        params = self._get_params()
        if color_code:
            params["color_code"] = color_code
        if webp and webp != "false":
            params["webp"] = webp
        return self._request(
            "GET",
            f"/vehicles/{vifid}/products/{product_id}/{product_type_id}",
            params=params,
        )

    def get_vehicle_by_ymmt(
        self,
        *,
        year: int,
        make: str,
        model: str,
        pid: int,
        ptid: int,
        trim: str | None = None,
        color_code: str | None = None,
        webp: str = "true",
    ) -> dict:
        """GET vehicle images by Year/Make/Model/Trim.

        URL: /vehicles?year=X&make=X&model=X&pid=X&ptid=X
        """
        if not self.live:
            return {"source": "stub"}
        params: dict[str, Any] = {
            "year": year,
            "make": make,
            "model": model,
            "pid": pid,
            "ptid": ptid,
        }
        if trim:
            params["trim"] = trim
        if color_code:
            params["color_code"] = color_code
        if webp and webp != "false":
            params["webp"] = webp
        return self._request("GET", "/vehicles", params=self._get_params(params))

    def get_vehicle_colors(self, vifid: int) -> list[EvoxColor]:
        """GET available colors for a VIFID.

        URL: /vehicles/{VIFID}/colors
        """
        if not self.live:
            return []
        try:
            data = self._request("GET", f"/vehicles/{vifid}/colors", params=self._get_params())
            colors: list[EvoxColor] = []
            for item in data if isinstance(data, list) else data.get("colors", []):
                colors.append(
                    EvoxColor(
                        color_code=item.get("color_code", ""),
                        color_title=item.get("color_title", ""),
                        color_simpletitle=item.get("color_simpletitle", ""),
                    )
                )
            return colors
        except Exception:
            logger.warning("EVOX get_vehicle_colors failed for vifid=%s", vifid, exc_info=True)
            return []

    def batch_product_query(
        self,
        requests: list[dict[str, Any]],
        ptids: list[int],
        *,
        webp: str = "true",
    ) -> dict:
        """POST batch vehicle product query (max 10 vehicles, max 10 ptids).

        URL: POST /vehicles/product-query
        Body: {"query_requests": [...], "ptid": [...], "webp": "true"}
        """
        if not self.live:
            return {
                "status": "success",
                "query_responses": [{"vif": req, "product_types": {}, "match_level": "stub"} for req in requests],
                "source": "stub",
            }

        body: dict[str, Any] = {
            "query_requests": requests[:10],
            "ptid": ptids[:10],
        }
        if webp:
            body["webp"] = webp

        return self._request(
            "POST",
            "/vehicles/product-query",
            json=body,
            headers=self._post_headers(),
        )

    # ---- Data downloads ----

    def download_vif_list(self) -> dict:
        """GET the VIF list (vehicle information tables).

        URL: /samples/viflists
        Returns JSON (or CSV depending on account config).
        """
        if not self.live:
            return {"source": "stub", "data": []}
        return self._request("GET", "/samples/viflists", params=self._get_params())

    def download_colors_list(self) -> dict:
        """GET the colors list.

        URL: /samples/colorslists
        """
        if not self.live:
            return {"source": "stub", "data": []}
        return self._request("GET", "/samples/colorslists", params=self._get_params())

    def download_alt_colors(self) -> dict:
        """GET alternate colors table.

        URL: /altcolors
        """
        if not self.live:
            return {"source": "stub", "data": []}
        return self._request("GET", "/altcolors", params=self._get_params())
