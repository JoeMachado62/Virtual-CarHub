from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.integrations.nhtsa_client import NHTSAClient, VinDecodeResult
from app.models.entities import Vehicle

logger = logging.getLogger(__name__)

_client: NHTSAClient | None = None


def _get_client() -> NHTSAClient:
    global _client
    if _client is None:
        _client = NHTSAClient(
            api_base_url=settings.nhtsa_api_base_url,
            live=settings.has_vin_decode,
        )
    return _client


def decode_vin(vin: str) -> VinDecodeResult:
    """Decode a single VIN via the NHTSA vPIC API."""
    return _get_client().decode_vin(vin)


def batch_decode_vins(vins: list[str]) -> list[VinDecodeResult]:
    """Decode multiple VINs via the NHTSA batch endpoint."""
    return _get_client().batch_decode(vins)


def decode_and_enrich(db: Session, vehicle: Vehicle) -> VinDecodeResult | None:
    """Decode the vehicle's VIN and enrich its features_normalized with factory data.

    - Only fills gaps; never overwrites existing non-null values.
    - Skips if features_normalized already has ``vin_decoded=True``.
    - Returns the decode result (or None if decoding is disabled / already done).
    """
    if not settings.has_vin_decode:
        return None

    normalized = dict(vehicle.features_normalized or {})
    if normalized.get("vin_decoded"):
        return None  # Already decoded, skip

    result = decode_vin(vehicle.vin)
    if result.raw_response.get("error"):
        logger.warning("VIN decode returned error for %s", vehicle.vin)
        return result

    # Enrich features_normalized with factory data
    _enrich_normalized(normalized, result)
    normalized["vin_decoded"] = True

    vehicle.features_normalized = normalized

    # Fill top-level Vehicle columns where NULL
    if not vehicle.drivetrain and result.drive_type:
        vehicle.drivetrain = result.drive_type
    if not vehicle.body_type and result.body_class:
        vehicle.body_type = result.body_class
    if not vehicle.engine_type and result.fuel_type:
        vehicle.engine_type = result.fuel_type
    if not vehicle.cylinders and result.engine_cylinders:
        vehicle.cylinders = result.engine_cylinders
    if not vehicle.trim and result.trim:
        vehicle.trim = result.trim

    db.add(vehicle)
    return result


def _enrich_normalized(normalized: dict[str, Any], result: VinDecodeResult) -> None:
    """Merge VIN decode data into features_normalized dict, filling only gaps."""

    def _set_if_missing(key: str, value: Any) -> None:
        if value is not None and not normalized.get(key):
            normalized[key] = value

    # Factory specs
    _set_if_missing("factory_drive_type", result.drive_type)
    _set_if_missing("factory_body_class", result.body_class)
    _set_if_missing("factory_doors", result.doors)
    _set_if_missing("factory_engine_cylinders", result.engine_cylinders)
    _set_if_missing("factory_engine_displacement_l", result.engine_displacement_l)
    _set_if_missing("factory_engine_model", result.engine_model)
    _set_if_missing("factory_fuel_type", result.fuel_type)
    _set_if_missing("factory_transmission", _format_transmission(result))
    _set_if_missing("factory_plant", _format_plant(result))
    _set_if_missing("factory_gvwr", result.gvwr)

    # Safety features - structured dict
    safety = normalized.get("safety_features") or {}
    safety_updates: dict[str, bool] = {}
    if result.abs is not None:
        safety_updates["abs"] = result.abs
    if result.esc is not None:
        safety_updates["esc"] = result.esc
    if result.traction_control is not None:
        safety_updates["traction_control"] = result.traction_control
    if result.forward_collision_warning is not None:
        safety_updates["forward_collision_warning"] = result.forward_collision_warning
    if result.lane_departure_warning is not None:
        safety_updates["lane_departure_warning"] = result.lane_departure_warning
    if result.lane_keep_assist is not None:
        safety_updates["lane_keep_assist"] = result.lane_keep_assist
    if result.blind_spot_monitoring is not None:
        safety_updates["blind_spot_monitoring"] = result.blind_spot_monitoring
    if result.adaptive_cruise is not None:
        safety_updates["adaptive_cruise"] = result.adaptive_cruise
    if result.backup_camera is not None:
        safety_updates["backup_camera"] = result.backup_camera
    if result.parking_assist is not None:
        safety_updates["parking_assist"] = result.parking_assist
    if result.auto_emergency_braking is not None:
        safety_updates["auto_emergency_braking"] = result.auto_emergency_braking

    if safety_updates:
        for key, value in safety_updates.items():
            if key not in safety:
                safety[key] = value
        normalized["safety_features"] = safety

    _set_if_missing("air_bag_locations", result.air_bag_locations)
    _set_if_missing("entertainment_system", result.entertainment_system)


def _format_transmission(result: VinDecodeResult) -> str | None:
    parts = []
    if result.transmission_speeds:
        parts.append(f"{result.transmission_speeds}-Speed")
    if result.transmission:
        parts.append(result.transmission)
    return " ".join(parts) if parts else None


def _format_plant(result: VinDecodeResult) -> str | None:
    parts = [p for p in [result.plant_city, result.plant_state, result.plant_country] if p]
    return ", ".join(parts) if parts else None
