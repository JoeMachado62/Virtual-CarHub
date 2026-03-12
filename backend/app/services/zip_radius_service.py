from __future__ import annotations

from functools import lru_cache
from math import asin, cos, radians, sin, sqrt

import zipcodes


def normalize_zip_code(value: str | None) -> str | None:
    if value in (None, ""):
        return None
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if len(digits) < 5:
        return None
    return digits[:5]


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_miles = 3958.7613
    d_lat = radians(lat2 - lat1)
    d_lon = radians(lon2 - lon1)
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    )
    return 2 * radius_miles * asin(sqrt(a))


@lru_cache(maxsize=1)
def _zip_coordinates() -> dict[str, tuple[float, float]]:
    coordinates: dict[str, tuple[float, float]] = {}
    for record in zipcodes.list_all():
        zip_code = normalize_zip_code(record.get("zip_code"))
        if not zip_code or not record.get("active"):
            continue
        lat = record.get("lat")
        lon = record.get("long")
        if lat in (None, "") or lon in (None, ""):
            continue
        try:
            coordinates[zip_code] = (float(lat), float(lon))
        except (TypeError, ValueError):
            continue
    return coordinates


@lru_cache(maxsize=2048)
def zip_codes_within_radius(zip_code: str, radius_miles: int) -> tuple[str, ...]:
    normalized = normalize_zip_code(zip_code)
    if not normalized:
        return tuple()

    coordinates = _zip_coordinates()
    origin = coordinates.get(normalized)
    if not origin:
        return tuple()

    if radius_miles <= 0:
        return (normalized,)

    origin_lat, origin_lon = origin
    matches = [
        candidate_zip
        for candidate_zip, (candidate_lat, candidate_lon) in coordinates.items()
        if _haversine_miles(origin_lat, origin_lon, candidate_lat, candidate_lon) <= radius_miles
    ]
    return tuple(sorted(matches))
