from app.integrations.base_client import ExternalServiceClient, ServicePolicy


class MarketCheckClient(ExternalServiceClient):
    def __init__(
        self,
        api_key: str,
        *,
        api_secret: str = "",
        api_base_url: str = "https://api.marketcheck.com/v2",
        live: bool = False,
    ):
        self.live = live
        self.api_key = api_key
        self.api_secret = api_secret
        super().__init__(
            base_url=api_base_url,
            headers={},
            policy=ServicePolicy(max_retries=3, timeout_seconds=30, failure_threshold=5, recovery_seconds=300),
        )

    def _with_api_key(self, params: dict | None = None) -> dict:
        payload = dict(params or {})
        if self.api_key:
            payload.setdefault("api_key", self.api_key)
        return payload

    def search_inventory(self, params: dict) -> dict:
        if not self.live:
            return {"listings": [], "source": "stub"}
        payload = self._with_api_key(params)
        return self._request("GET", "/search/car/active", params=payload)

    def get_listing(self, listing_id: str) -> dict:
        if not self.live:
            return {"id": listing_id, "active": True, "source": "stub"}
        params = self._with_api_key()
        try:
            return self._request("GET", f"/listing/car/{listing_id}", params=params)
        except Exception:
            search_params = {"rows": 1, "start": 0, "listing_id": listing_id}
            search_params = self._with_api_key(search_params)
            payload = self._request("GET", "/search/car/active", params=search_params)
            listings = payload.get("listings", []) if isinstance(payload, dict) else []
            return listings[0] if listings else {"id": listing_id, "active": False, "source": "search_fallback"}

    def get_facets(self, params: dict | None = None, *, facets: list[str] | None = None) -> dict:
        if not self.live:
            return {"num_found": 0, "listings": [], "facets": {}, "source": "stub"}
        payload = {"rows": 0, "start": 0}
        payload.update(params or {})
        if facets:
            payload["facets"] = ",".join(facets)
        payload = self._with_api_key(payload)
        return self._request("GET", "/search/car/active", params=payload)

    def get_terms(self, field: str, params: dict | None = None) -> dict:
        if not self.live:
            return {"terms": [], "field": field, "source": "stub"}
        payload = {"field": field}
        payload.update(params or {})
        payload = self._with_api_key(payload)
        return self._request("GET", "/specs/car/terms", params=payload)

    def get_history(self, vin: str) -> dict:
        """GET /v2/history/car/{vin} — vehicle history with past listing IDs."""
        if not self.live:
            return {"vin": vin, "history": [], "source": "stub"}
        params = self._with_api_key()
        return self._request("GET", f"/history/car/{vin}", params=params)

    def get_market_days_supply(self, params: dict) -> dict:
        """GET /v2/mds/car — market days supply and 45-day inferred sales."""
        if not self.live:
            return {
                "mds": None,
                "total_active_cars_for_ymmt": 0,
                "total_cars_sold_in_last_45_days": 0,
                "source": "stub",
            }
        payload = self._with_api_key(params)
        return self._request("GET", "/mds/car", params=payload)
