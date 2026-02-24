from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.integrations.marketcheck_client import MarketCheckClient


def main() -> int:
    if not settings.marketcheck_api_key:
        print("MARKETCHECK_API_KEY is not set in backend/.env")
        return 1

    force_live = os.getenv("MARKETCHECK_FORCE_LIVE", "").lower() in {"1", "true", "yes"}
    live = settings.has_marketcheck or force_live
    if not live:
        print("MARKETCHECK_LIVE_ENABLED is false. Set MARKETCHECK_FORCE_LIVE=1 to run a live connectivity test.")
        return 1

    client = MarketCheckClient(
        api_key=settings.marketcheck_api_key,
        api_secret=settings.marketcheck_api_secret,
        price_api_key=settings.marketcheck_price_api_key,
        api_base_url=settings.marketcheck_api_base_url,
        live=True,
    )

    params = {"rows": 5, "start": 0}
    zipcode = os.getenv("MARKETCHECK_TEST_ZIP", "").strip()
    if zipcode:
        params["zip"] = zipcode
        params["radius"] = int(os.getenv("MARKETCHECK_TEST_RADIUS", "100"))

    payload = client.search_inventory(params)
    listings = payload.get("listings", []) if isinstance(payload, dict) else []
    print(f"Fetched {len(listings)} listing(s)")

    if listings:
        first = listings[0]
        print("First listing summary:")
        print(
            {
                "id": first.get("id"),
                "vin": first.get("vin"),
                "year": first.get("year") or (first.get("build") or {}).get("year"),
                "make": first.get("make") or (first.get("build") or {}).get("make"),
                "model": first.get("model") or (first.get("build") or {}).get("model"),
                "price": first.get("price"),
            }
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
