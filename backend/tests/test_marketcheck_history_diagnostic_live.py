from __future__ import annotations

import json
import logging
import os
import re
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

import pytest

from app.core.config import settings
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.integrations.marketcheck_client import MarketCheckClient
from app.models.entities import Vehicle
from app.services.marketcheck_history_enrichment_service import (
    enrich_vehicle_history,
    select_best_history_entry,
)

BMW_DIAGNOSTIC_VIN = "WBA33EH01SCV39182"
LIVE_FLAG_VALUES = {"1", "true", "yes"}
LOGGER = logging.getLogger("vch.marketcheck.diagnostic")
API_KEY_RE = re.compile(r"(api_key=)([^&\"'\s]+)")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    return value


def _payload_summary(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        summary: dict[str, Any] = {
            "type": "dict",
            "keys": sorted(str(key) for key in payload.keys()),
        }
        for key in ("vin", "id", "listing_id", "source", "error"):
            if payload.get(key) not in (None, "", [], {}):
                summary[key] = payload.get(key)
        listings = payload.get("listings")
        history = payload.get("history")
        options = payload.get("available_options_packages") or payload.get("options_packages") or payload.get("packages")
        if isinstance(listings, list):
            summary["listings_count"] = len(listings)
        if isinstance(history, list):
            summary["history_count"] = len(history)
        if isinstance(options, list):
            summary["options_package_count"] = len(options)
        return summary
    if isinstance(payload, list):
        return {"type": "list", "count": len(payload)}
    return {"type": type(payload).__name__, "repr": repr(payload)}


def _history_entry_summary(entry: dict[str, Any] | None) -> dict[str, Any]:
    entry = entry or {}
    return {
        "id": entry.get("id"),
        "listing_id": entry.get("listing_id"),
        "vin": entry.get("vin"),
        "seller_type": entry.get("seller_type"),
        "last_seen_at": entry.get("last_seen_at"),
        "scraped_at": entry.get("scraped_at"),
        "first_seen_at": entry.get("first_seen_at"),
        "vdp_url": entry.get("vdp_url"),
        "listing_url": entry.get("listing_url"),
        "website": entry.get("website"),
        "has_build": bool(entry.get("build")),
        "has_extra": bool(entry.get("extra")),
        "has_features": bool(entry.get("features")),
    }


def _redact_api_key_text(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    return API_KEY_RE.sub(r"\1[REDACTED]", value)


class _RedactingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return _redact_api_key_text(super().format(record))


@contextmanager
def _capture_logs(log_path: Path) -> Iterator[None]:
    formatter = _RedactingFormatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(formatter)

    root = logging.getLogger()
    previous_root_level = root.level
    root.addHandler(handler)
    root.setLevel(logging.DEBUG)
    try:
        yield
    finally:
        root.removeHandler(handler)
        root.setLevel(previous_root_level)
        handler.close()


class DiagnosticMarketCheckClient(MarketCheckClient):
    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.captured_calls: list[dict[str, Any]] = []

    def _record_success(self, *, endpoint: str, request: dict[str, Any], response: Any) -> Any:
        item = {
            "endpoint": endpoint,
            "request": request,
            "response_summary": _payload_summary(response),
            "response_payload": response,
        }
        self.captured_calls.append(item)
        LOGGER.info("marketcheck_%s_success request=%s response=%s", endpoint, request, item["response_summary"])
        return response

    def _record_failure(self, *, endpoint: str, request: dict[str, Any], error: Exception) -> None:
        self.captured_calls.append(
            {
                "endpoint": endpoint,
                "request": request,
                "error": str(error),
                "error_type": type(error).__name__,
            }
        )
        LOGGER.exception("marketcheck_%s_failed request=%s", endpoint, request)

    def get_history(self, vin: str) -> dict:
        request = {"vin": vin, "path": f"/history/car/{vin}"}
        try:
            response = super().get_history(vin)
        except Exception as exc:
            self._record_failure(endpoint="history", request=request, error=exc)
            raise
        return self._record_success(endpoint="history", request=request, response=response)

    def get_listing(self, listing_id: str) -> dict:
        request = {"listing_id": listing_id, "path": f"/listing/car/{listing_id}"}
        try:
            response = super().get_listing(listing_id)
        except Exception as exc:
            self._record_failure(endpoint="listing", request=request, error=exc)
            raise
        return self._record_success(endpoint="listing", request=request, response=response)

    def get_available_options_packages(self, vin: str) -> dict:
        request = {"vin": vin, "path": f"/decode/car/neovin/{vin}/options-packages"}
        try:
            response = super().get_available_options_packages(vin)
        except Exception as exc:
            self._record_failure(endpoint="options_packages", request=request, error=exc)
            raise
        return self._record_success(endpoint="options_packages", request=request, response=response)


def _run_live_marketcheck_history_diagnostic(vin: str) -> dict[str, Any]:
    init_db()
    artifact_dir = Path(__file__).resolve().parents[1] / "logs" / "diagnostics"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    base_name = f"marketcheck_history_diagnostic_{vin}_{stamp}"
    log_path = artifact_dir / f"{base_name}.log"
    json_path = artifact_dir / f"{base_name}.json"

    client = DiagnosticMarketCheckClient(
        api_key=settings.marketcheck_api_key,
        api_secret=settings.marketcheck_api_secret,
        price_api_key=settings.marketcheck_price_api_key,
        api_base_url=settings.marketcheck_api_base_url,
        live=True,
    )

    with _capture_logs(log_path):
        LOGGER.info("marketcheck_history_diagnostic_start vin=%s json_path=%s", vin, json_path)
        with SessionLocal() as db:
            vehicle = db.get(Vehicle, vin)
            created_temp_vehicle = vehicle is None
            if vehicle is None:
                vehicle = Vehicle(
                    vin=vin,
                    listing_id=f"diagnostic-{vin.lower()}-{stamp.lower()}",
                    year=2025,
                    make="BMW",
                    model="740i",
                    trim=None,
                    price_asking=1.0,
                    source_type="auction",
                    source_url=None,
                    available=True,
                    images=[],
                    features_raw=[],
                    features_normalized={},
                    bfv_compatibility_scores={},
                )
                db.add(vehicle)
                db.flush()
                LOGGER.info("seeded_temporary_vehicle vin=%s listing_id=%s", vin, vehicle.listing_id)
            else:
                LOGGER.info(
                    "using_existing_vehicle vin=%s source_type=%s listing_id=%s source_url=%s",
                    vehicle.vin,
                    vehicle.source_type,
                    vehicle.listing_id,
                    vehicle.source_url,
                )

            record = enrich_vehicle_history(db, vehicle=vehicle, client=client, force=True)
            db.flush()

            history_call = next((call for call in client.captured_calls if call["endpoint"] == "history"), None)
            history_payload = history_call.get("response_payload") if history_call else None
            selected_entry = select_best_history_entry(
                history_payload,
                preferred_source_url=vehicle.source_url,
            )
            listing_calls = [call for call in client.captured_calls if call["endpoint"] == "listing"]
            mismatched_listing_calls = []
            for call in listing_calls:
                payload = call.get("response_payload")
                if not isinstance(payload, dict):
                    continue
                returned_vin = str(payload.get("vin") or "").upper()
                requested_id = str(call["request"].get("listing_id") or "")
                returned_id = str(payload.get("id") or payload.get("listing_id") or "")
                if returned_vin and returned_vin != vin.upper():
                    mismatched_listing_calls.append(
                        {
                            "requested_listing_id": requested_id,
                            "returned_vin": returned_vin,
                            "returned_id": returned_id,
                            "summary": call.get("response_summary"),
                        }
                    )

            result = {
                "vin": vin,
                "generated_at": datetime.now(UTC),
                "created_temp_vehicle": created_temp_vehicle,
                "vehicle_context": {
                    "vin": vehicle.vin,
                    "listing_id": vehicle.listing_id,
                    "source_type": vehicle.source_type,
                    "source_url": vehicle.source_url,
                    "year": vehicle.year,
                    "make": vehicle.make,
                    "model": vehicle.model,
                    "trim": vehicle.trim,
                },
                "captured_calls": client.captured_calls,
                "history_selected_entry": _history_entry_summary(selected_entry),
                "history_entry_used_by_record": _history_entry_summary(record.history_entry_json),
                "record": {
                    "status": record.status,
                    "source_listing_id": record.source_listing_id,
                    "source_url": record.source_url,
                    "last_error": record.last_error,
                    "attempts": record.attempts,
                    "seller_comments_present": bool(record.seller_comments),
                    "feature_count": len((record.listing_metadata_json or {}).get("features") or []),
                    "option_package_count": len((record.listing_metadata_json or {}).get("option_packages") or []),
                    "listing_payload_summary": _payload_summary(record.listing_payload_json),
                    "listing_metadata_keys": sorted((record.listing_metadata_json or {}).keys()),
                },
                "mismatched_listing_calls": mismatched_listing_calls,
                "mismatch_detected": bool(mismatched_listing_calls),
                "artifacts": {
                    "log_path": str(log_path),
                    "json_path": str(json_path),
                },
            }

            json_path.write_text(json.dumps(_json_safe(result), indent=2), encoding="utf-8")
            LOGGER.info("marketcheck_history_diagnostic_complete result=%s", _json_safe(result["record"]))
            LOGGER.info("marketcheck_history_diagnostic_artifacts log=%s json=%s", log_path, json_path)
            db.rollback()

    return result


@pytest.mark.skipif(
    os.getenv("MARKETCHECK_LIVE_DIAGNOSTIC", "").strip().lower() not in LIVE_FLAG_VALUES,
    reason="Set MARKETCHECK_LIVE_DIAGNOSTIC=1 to run the live MarketCheck diagnostic.",
)
@pytest.mark.skipif(not settings.has_marketcheck, reason="MarketCheck live credentials are not configured.")
def test_marketcheck_history_live_bmw_vin_diagnostic(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    result = _run_live_marketcheck_history_diagnostic(BMW_DIAGNOSTIC_VIN)

    assert result["vin"] == BMW_DIAGNOSTIC_VIN
    assert result["captured_calls"]
    assert any(call["endpoint"] == "history" for call in result["captured_calls"])
    assert Path(result["artifacts"]["log_path"]).exists()
    assert Path(result["artifacts"]["json_path"]).exists()
