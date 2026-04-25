from app.integrations.base_client import ExternalServiceClient, ServicePolicy


class MarketCheckClient(ExternalServiceClient):
    def __init__(
        self,
        api_key: str,
        *,
        api_secret: str = "",
        price_api_key: str = "",
        api_base_url: str = "https://api.marketcheck.com/v2",
        live: bool = False,
    ):
        self.live = live
        self.api_key = api_key
        self.api_secret = api_secret
        self.price_api_key = price_api_key or api_key
        super().__init__(
            base_url=api_base_url,
            headers={},
            policy=ServicePolicy(max_retries=3, timeout_seconds=30, failure_threshold=5, recovery_seconds=300),
        )

    def _with_api_key(self, params: dict | None = None, *, use_price_key: bool = False) -> dict:
        payload = dict(params or {})
        key = self.price_api_key if use_price_key else self.api_key
        if key:
            payload.setdefault("api_key", key)
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

    def get_available_options_packages(self, vin: str) -> dict:
        """GET /v2/decode/car/neovin/{vin}/options-packages — available factory option packages."""
        if not self.live:
            return {"vin": vin, "available_options_packages": [], "source": "stub"}
        params = self._with_api_key()
        return self._request("GET", f"/decode/car/neovin/{vin}/options-packages", params=params)

    def get_price(self, vin: str) -> dict:
        if not self.live:
            return {"vin": vin, "average_retail": 30000, "source": "stub"}
        params = self._with_api_key({"vin": vin}, use_price_key=True)
        try:
            return self._request("GET", "/stats/car", params=params)
        except Exception:
            search_params = self._with_api_key({"rows": 10, "start": 0, "vin": vin}, use_price_key=True)
            payload = self._request("GET", "/search/car/active", params=search_params)
            listings = payload.get("listings", []) if isinstance(payload, dict) else []
            prices = [float(row.get("price")) for row in listings if row.get("price") is not None]
            average = round(sum(prices) / len(prices), 2) if prices else None
            return {
                "vin": vin,
                "average_retail": average,
                "sample_count": len(prices),
                "source": "search_fallback",
            }

    def get_marketcheck_price(self, params: dict) -> dict:
        """GET /v2/predict/car/us/marketcheck_price — model-based market value."""
        if not self.live:
            return {"marketcheck_price": None, "source": "stub"}
        payload = self._with_api_key(params, use_price_key=True)
        return self._request("GET", "/predict/car/us/marketcheck_price", params=payload)

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
