from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.integrations.base_client import ExternalServiceClient, ServicePolicy

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class VinDecodeResult:
    vin: str
    year: int | None = None
    make: str | None = None
    model: str | None = None
    trim: str | None = None
    body_class: str | None = None
    doors: int | None = None
    drive_type: str | None = None
    engine_displacement_l: float | None = None
    engine_cylinders: int | None = None
    engine_model: str | None = None
    fuel_type: str | None = None
    transmission: str | None = None
    transmission_speeds: str | None = None
    plant_city: str | None = None
    plant_country: str | None = None
    plant_state: str | None = None
    gvwr: str | None = None
    # Safety / equipment features
    abs: bool | None = None
    esc: bool | None = None
    traction_control: bool | None = None
    forward_collision_warning: bool | None = None
    lane_departure_warning: bool | None = None
    lane_keep_assist: bool | None = None
    blind_spot_monitoring: bool | None = None
    adaptive_cruise: bool | None = None
    backup_camera: bool | None = None
    parking_assist: bool | None = None
    auto_emergency_braking: bool | None = None
    air_bag_locations: str | None = None
    # Entertainment / comfort
    entertainment_system: str | None = None
    # Full raw response for future use
    raw_response: dict = field(default_factory=dict)


_BOOL_MAP = {"std": True, "opt": True, "standard": True, "optional": True}


def _parse_bool(value: str | None) -> bool | None:
    if not value:
        return None
    return _BOOL_MAP.get(value.strip().lower())


def _parse_int(value: str | None) -> int | None:
    if not value:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None


def _parse_float(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _clean(value: str | None) -> str | None:
    if not value or value.strip() in ("", "Not Applicable"):
        return None
    return value.strip()


def _parse_decode_response(vin: str, data: dict) -> VinDecodeResult:
    """Parse the NHTSA vPIC DecodeVinValues response into a VinDecodeResult."""
    results = data.get("Results", [])
    if not results:
        return VinDecodeResult(vin=vin, raw_response=data)

    r = results[0]

    return VinDecodeResult(
        vin=vin,
        year=_parse_int(r.get("ModelYear")),
        make=_clean(r.get("Make")),
        model=_clean(r.get("Model")),
        trim=_clean(r.get("Trim")),
        body_class=_clean(r.get("BodyClass")),
        doors=_parse_int(r.get("Doors")),
        drive_type=_clean(r.get("DriveType")),
        engine_displacement_l=_parse_float(r.get("DisplacementL")),
        engine_cylinders=_parse_int(r.get("EngineCylinders")),
        engine_model=_clean(r.get("EngineModel")),
        fuel_type=_clean(r.get("FuelTypePrimary")),
        transmission=_clean(r.get("TransmissionStyle")),
        transmission_speeds=_clean(r.get("TransmissionSpeeds")),
        plant_city=_clean(r.get("PlantCity")),
        plant_country=_clean(r.get("PlantCountry")),
        plant_state=_clean(r.get("PlantState")),
        gvwr=_clean(r.get("GVWR")),
        # Safety
        abs=_parse_bool(r.get("ABS")),
        esc=_parse_bool(r.get("ESC")),
        traction_control=_parse_bool(r.get("TractionControl")),
        forward_collision_warning=_parse_bool(r.get("ForwardCollisionWarning")),
        lane_departure_warning=_parse_bool(r.get("LaneDepartureWarning")),
        lane_keep_assist=_parse_bool(r.get("LaneKeepSystem")),
        blind_spot_monitoring=_parse_bool(r.get("BlindSpotMon")),
        adaptive_cruise=_parse_bool(r.get("AdaptiveCruiseControl")),
        backup_camera=_parse_bool(r.get("RearVisibilitySystem")),
        parking_assist=_parse_bool(r.get("ParkAssist")),
        auto_emergency_braking=_parse_bool(r.get("AutomaticEmergencyBraking")),
        air_bag_locations=_clean(r.get("AirBagLocFront")) or _clean(r.get("AirBagLocSide")),
        # Entertainment
        entertainment_system=_clean(r.get("EntertainmentSystem")),
        raw_response=data,
    )


class NHTSAClient(ExternalServiceClient):
    """Client for the NHTSA vPIC (Vehicle Product Information Catalog) API.
    Free, no API key required. Decodes VINs to factory specifications."""

    def __init__(self, *, api_base_url: str = "https://vpic.nhtsa.dot.gov/api", live: bool = True):
        self.live = live
        super().__init__(
            base_url=api_base_url,
            headers={"Accept": "application/json"},
            policy=ServicePolicy(max_retries=2, timeout_seconds=15, failure_threshold=5, recovery_seconds=300),
        )

    def decode_vin(self, vin: str) -> VinDecodeResult:
        """Decode a single VIN using the NHTSA DecodeVinValues endpoint."""
        if not self.live:
            return VinDecodeResult(vin=vin, raw_response={"source": "stub"})
        try:
            data = self._request("GET", f"/vehicles/DecodeVinValues/{vin}", params={"format": "json"})
            return _parse_decode_response(vin, data)
        except Exception:
            logger.warning("NHTSA VIN decode failed for %s", vin, exc_info=True)
            return VinDecodeResult(vin=vin, raw_response={"error": True})

    def batch_decode(self, vins: list[str]) -> list[VinDecodeResult]:
        """Decode multiple VINs using the NHTSA batch endpoint (POST, semicolon-separated)."""
        if not self.live or not vins:
            return [VinDecodeResult(vin=v, raw_response={"source": "stub"}) for v in vins]

        # NHTSA batch endpoint accepts semicolon-separated VINs in form data
        vin_string = ";".join(vins)
        try:
            data = self._request(
                "POST",
                "/vehicles/DecodeVINValuesBatch/",
                data={"format": "json", "data": vin_string},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            results_list = data.get("Results", [])
            # Build a lookup by VIN from the batch response
            by_vin: dict[str, dict[str, Any]] = {}
            for item in results_list:
                item_vin = (item.get("VIN") or "").strip().upper()
                if item_vin:
                    by_vin[item_vin] = item

            decoded: list[VinDecodeResult] = []
            for vin in vins:
                match = by_vin.get(vin.upper())
                if match:
                    decoded.append(_parse_decode_response(vin, {"Results": [match]}))
                else:
                    decoded.append(VinDecodeResult(vin=vin, raw_response={"error": True, "reason": "not_in_batch"}))
            return decoded
        except Exception:
            logger.warning("NHTSA batch decode failed for %d VINs", len(vins), exc_info=True)
            return [VinDecodeResult(vin=v, raw_response={"error": True}) for v in vins]
