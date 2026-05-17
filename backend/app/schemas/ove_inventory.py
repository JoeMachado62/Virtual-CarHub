from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.constants import AuctionPlatform, InventorySourceType, OveDetailRequestStatus
from app.schemas.condition_report_granular import (
    build_granular_condition_report,
    normalize_granular_condition_report,
)


def _normalize_vin(value: str) -> str:
    text = value.strip().upper()
    if len(text) != 17:
        raise ValueError("VIN must be 17 characters")
    return text


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_str_list(value: Any, *, max_item_chars: int | None = None) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _clean_text(item)
        if not text:
            continue
        if max_item_chars is not None and len(text) > max_item_chars:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _coerce_bool(value: Any) -> bool | None:
    if value in (None, ""):
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y"}:
        return True
    if text in {"0", "false", "no", "n"}:
        return False
    return None


def _coerce_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _first_clean_text(*values: Any) -> str | None:
    for value in values:
        cleaned = _clean_text(value)
        if cleaned:
            return cleaned
    return None


def _first_coerce_int(*values: Any) -> int | None:
    for value in values:
        coerced = _coerce_int(value)
        if coerced is not None:
            return coerced
    return None


# ---------------------------------------------------------------------------
# NAAA standard inspection fields — every field is always present in the
# normalised output so that the frontend can render the full Manheim-style
# condition report regardless of which vendor/scraper produced the data.
# ---------------------------------------------------------------------------

_CLEAN_VALUES = frozenset({
    "no issues", "none", "no damage", "not inspected", "not specified",
    "fully functional", "no oil sludge", "factory equipment installed",
    "not applicable", "n/a", "", "not available",
    # Positive / normal-state values from the NAAA inspection
    "yes - starts", "yes - drives", "yes",
    "no codes found", "no codes",
})


def _is_issue_value(value: str) -> bool:
    """Return True when a field value represents a real issue (not a clean/default state)."""
    normalized = value.strip().lower()
    if normalized in _CLEAN_VALUES:
        return False
    # Numeric key counts (e.g. "1", "2", "0") are informational, not issues
    if normalized.isdigit():
        return False
    # Tire depth readings like '6/32" or Above' are not issues
    if "/32" in normalized:
        return False
    return True

NAAA_INSPECTION_TEMPLATE: dict[str, dict[str, Any]] = {
    "drivability": {
        "label": "Drivability, Keys, & History",
        "fields": {
            "smart_keys":     {"label": "Smart Keys",                     "default": "Not Inspected"},
            "other_keys":     {"label": "Other Keys",                     "default": "Not Inspected"},
            "odor_bio":       {"label": "Odor/Bio/Environmental/History", "default": "Not Inspected"},
            "vehicle_starts": {"label": "Vehicle Starts",                 "default": "Not Inspected"},
            "vehicle_drives": {"label": "Vehicle Drives",                 "default": "Not Inspected"},
        },
    },
    "exterior": {
        "label": "Exterior",
        "fields": {
            "front_exterior":      {"label": "Front Exterior",      "default": "Not Inspected"},
            "driver_exterior":     {"label": "Driver Exterior",     "default": "Not Inspected"},
            "roof_exterior":       {"label": "Roof - Exterior",     "default": "Not Inspected"},
            "passenger_exterior":  {"label": "Passenger Exterior",  "default": "Not Inspected"},
            "rear_exterior":       {"label": "Rear Exterior",       "default": "Not Inspected"},
            "further_disclosures": {"label": "Further Disclosures", "default": "Not Specified"},
        },
    },
    "interior": {
        "label": "Interior",
        "fields": {
            "airbags":              {"label": "Airbags",                  "default": "Not Inspected"},
            "climate_control":      {"label": "Climate Control",          "default": "Not Inspected"},
            "electrical_accessory": {"label": "Electrical Accessory",     "default": "Not Inspected"},
            "infotainment_radio":   {"label": "Infotainment/Radio",       "default": "Not Inspected"},
            "sunroof_operation":    {"label": "Sunroof Operation",        "default": "Not Inspected"},
            "interior_cosmetic":    {"label": "Interior Cosmetic Damage", "default": "Not Inspected"},
        },
    },
    "mechanical": {
        "label": "Mechanical & Diagnostic Trouble Codes",
        "fields": {
            "diagnostic_trouble_codes": {"label": "Diagnostic Trouble Codes",                              "default": "Not Inspected"},
            "emissions_catalytic":      {"label": "Emissions/Catalytic/Exhaust",                           "default": "Not Inspected"},
            "engine_noise":             {"label": "Engine Noise",                                          "default": "Not Inspected"},
            "warning_lights":           {"label": "Warning Lights & Gauge Cluster",                        "default": "Not Inspected"},
            "active_visible_leaks":     {"label": "Active Visible Leaks From Engine Or Undercarriage Area", "default": "Not Inspected"},
            "engine_oil_sludge":        {"label": "Engine Oil Sludge",                                     "default": "Not Inspected"},
            "vehicle_smoke":            {"label": "Vehicle Smoke",                                         "default": "Not Inspected"},
            "other_mechanical":         {"label": "Other Mechanical Comments",                             "default": "Not Specified"},
        },
    },
    "tires": {
        "label": "Tires & Wheels",
        "fields": {
            "driver_front_tire_depth":    {"label": "Driver Front Tire Depth",       "default": "Not Inspected"},
            "driver_front_tire_issue":    {"label": "Driver Front Tire & Wheel Issue", "default": "Not Inspected"},
            "driver_rear_tire_depth":     {"label": "Driver Rear Tire Depth",        "default": "Not Inspected"},
            "driver_rear_tire_issue":     {"label": "Driver Rear Tire & Wheel Issue", "default": "Not Inspected"},
            "passenger_front_tire_depth": {"label": "Passenger Front Tire Depth",    "default": "Not Inspected"},
            "passenger_front_tire_issue": {"label": "Passenger Front Tire & Wheel Issue", "default": "Not Inspected"},
            "passenger_rear_tire_depth":  {"label": "Passenger Rear Tire Depth",     "default": "Not Inspected"},
            "passenger_rear_tire_issue":  {"label": "Passenger Rear Tire & Wheel Issue", "default": "Not Inspected"},
        },
    },
}


def _normalize_inspection(
    raw_inspection: dict[str, Any] | None,
    report: dict[str, Any],
) -> dict[str, Any]:
    """Build a fully-populated NAAA inspection dict.

    If the scraper sent ``inspection``, merge it with the template so every
    field exists.  Otherwise, synthesise what we can from legacy flat fields
    (``vehicle_history``, ``tire_depths``, ``damage_items``, etc.).
    """
    incoming: dict[str, Any] = {}
    if isinstance(raw_inspection, dict):
        incoming = raw_inspection

    # Build from legacy fields when scraper didn't send structured inspection
    if not incoming:
        incoming = _build_inspection_from_legacy(report)

    result: dict[str, Any] = {}
    for section_id, section_def in NAAA_INSPECTION_TEMPLATE.items():
        section_fields: dict[str, Any] = {}
        incoming_section = incoming.get(section_id, {})
        if not isinstance(incoming_section, dict):
            incoming_section = {}
        section_issue_count = 0

        for field_id, field_def in section_def["fields"].items():
            # Get value from incoming data, fall back to template default
            raw_value = incoming_section.get(field_id)
            is_default = raw_value in (None, "")
            value = str(raw_value).strip() if not is_default else field_def["default"]
            has_issue = _is_issue_value(value)
            if has_issue:
                section_issue_count += 1
            section_fields[field_id] = {
                "label": field_def["label"],
                "value": value,
                "has_issue": has_issue,
                "is_default": is_default,
            }

        result[section_id] = {
            "label": section_def["label"],
            "fields": section_fields,
            "issue_count": section_issue_count,
        }

    return result


def _build_inspection_from_legacy(report: dict[str, Any]) -> dict[str, Any]:
    """Synthesise an inspection dict from the older flat CR fields.

    Priority order:
      1. Parse ``metadata.report_page.body_text`` — the full text of the
         Manheim CR page which contains every NAAA field and its value.
      2. Fall back to structured fields (``vehicle_history``, ``tire_depths``,
         ``damage_items``, ``mechanical_findings``, OVE listing flags, etc.).
    """
    # --- Try parsing body_text first (covers all 32 fields) ---
    parsed = _parse_body_text_inspection(report)
    if parsed:
        return parsed

    # --- Fallback: build from structured CR fields ---
    legacy: dict[str, Any] = {}
    metadata = report.get("metadata") or {}
    listing_json = metadata.get("listing_json") or {}

    # --- Drivability ---
    drv: dict[str, Any] = {}
    vh = report.get("vehicle_history")
    if isinstance(vh, dict):
        if vh.get("engine_starts") is not None:
            drv["vehicle_starts"] = "Yes - Starts" if vh["engine_starts"] else "Does Not Start"
        if vh.get("drivable") is not None:
            drv["vehicle_drives"] = "Yes - Drives" if vh["drivable"] else "Does Not Drive"
    if drv:
        legacy["drivability"] = drv

    # --- Tires from tire_depths ---
    td = report.get("tire_depths")
    if isinstance(td, dict):
        tire_map = {
            "lf": "driver_front", "left_front": "driver_front", "driver_front": "driver_front",
            "rf": "passenger_front", "right_front": "passenger_front", "passenger_front": "passenger_front",
            "lr": "driver_rear", "left_rear": "driver_rear", "driver_rear": "driver_rear",
            "rr": "passenger_rear", "right_rear": "passenger_rear", "passenger_rear": "passenger_rear",
        }
        tires: dict[str, Any] = {}
        for src_key, tire_data in td.items():
            if not isinstance(tire_data, dict):
                continue
            dest = tire_map.get(src_key.lower())
            if not dest:
                continue
            depth = _clean_text(tire_data.get("tread_depth"))
            issue = _clean_text(tire_data.get("issue"))
            if depth:
                tires[f"{dest}_tire_depth"] = depth
            tires[f"{dest}_tire_issue"] = issue or "No Issues"
        if tires:
            legacy["tires"] = tires

    # --- Exterior ---
    ext: dict[str, Any] = {}
    has_cr_grade = bool(report.get("overall_grade"))
    damage_items = report.get("damage_items")
    no_damage_reported = isinstance(damage_items, list) and len(damage_items) == 0 and has_cr_grade

    if report.get("structural_damage"):
        ext["further_disclosures"] = f"Structural: {report['structural_damage']}"
    elif listing_json.get("hasFrameDamage") is False:
        ext["further_disclosures"] = "Not Specified"

    if report.get("paint_condition"):
        ext["front_exterior"] = str(report["paint_condition"])

    # When the CR was performed and damage_items is empty, all panels are clean
    if no_damage_reported:
        for panel in ("front_exterior", "driver_exterior", "roof_exterior",
                      "passenger_exterior", "rear_exterior"):
            ext.setdefault(panel, "No Damage")

    if ext:
        legacy["exterior"] = ext

    # --- Interior ---
    intr: dict[str, Any] = {}
    if report.get("interior_condition"):
        intr["interior_cosmetic"] = str(report["interior_condition"])
    if no_damage_reported:
        for field in ("airbags", "climate_control", "electrical_accessory",
                      "infotainment_radio", "sunroof_operation", "interior_cosmetic"):
            intr.setdefault(field, "No Issues")
    if intr:
        legacy["interior"] = intr

    # --- Mechanical ---
    mech: dict[str, Any] = {}
    mech_findings = report.get("mechanical_findings")
    diag_codes = report.get("diagnostic_codes")

    if isinstance(mech_findings, list):
        for finding in mech_findings:
            if not isinstance(finding, dict):
                continue
            system = (finding.get("system") or "").upper()
            condition = _clean_text(finding.get("condition"))
            if not condition:
                continue
            if "DIAGNOSTIC" in system or "TROUBLE" in system:
                mech["diagnostic_trouble_codes"] = condition
            elif "ENGINE NOISE" in system:
                mech["engine_noise"] = condition
            elif "WARNING" in system or "GAUGE" in system:
                mech["warning_lights"] = condition
            elif "LEAK" in system:
                mech["active_visible_leaks"] = condition
            elif "SMOKE" in system:
                mech["vehicle_smoke"] = condition
            elif "EMISSION" in system or "CATALYTIC" in system:
                mech["emissions_catalytic"] = condition
            elif "SLUDGE" in system:
                mech["engine_oil_sludge"] = condition

    if isinstance(diag_codes, list) and len(diag_codes) == 0 and has_cr_grade:
        mech.setdefault("diagnostic_trouble_codes", "No Codes Found")

    if no_damage_reported:
        for field in ("engine_noise", "warning_lights", "vehicle_smoke",
                      "active_visible_leaks"):
            mech.setdefault(field, "No Issues")
        mech.setdefault("engine_oil_sludge", "No Oil Sludge")
        mech.setdefault("emissions_catalytic", "Factory Equipment Installed")

    if mech:
        legacy["mechanical"] = mech

    return legacy


# -- Map NAAA field labels (as they appear in body_text) to template field IDs --

_BODY_TEXT_FIELD_MAP: dict[str, tuple[str, str]] = {
    # label in body_text → (section_id, field_id)
    # Drivability
    "SMART KEYS":                        ("drivability", "smart_keys"),
    "OTHER KEYS":                        ("drivability", "other_keys"),
    "ODOR/BIO/ENVIRONMENTAL/HISTORY":    ("drivability", "odor_bio"),
    "VEHICLE STARTS":                    ("drivability", "vehicle_starts"),
    "VEHICLE DRIVES":                    ("drivability", "vehicle_drives"),
    # Exterior
    "FRONT EXTERIOR":                    ("exterior", "front_exterior"),
    "DRIVER EXTERIOR":                   ("exterior", "driver_exterior"),
    "ROOF - EXTERIOR":                   ("exterior", "roof_exterior"),
    "PASSENGER EXTERIOR":                ("exterior", "passenger_exterior"),
    "REAR EXTERIOR":                     ("exterior", "rear_exterior"),
    "FURTHER DISCLOSURES":               ("exterior", "further_disclosures"),
    # Interior
    "AIRBAGS":                           ("interior", "airbags"),
    "CLIMATE CONTROL":                   ("interior", "climate_control"),
    "ELECTRICAL ACCESSORY":              ("interior", "electrical_accessory"),
    "INFOTAINMENT/RADIO":                ("interior", "infotainment_radio"),
    "SUNROOF OPERATION":                 ("interior", "sunroof_operation"),
    "INTERIOR COSMETIC DAMAGE":          ("interior", "interior_cosmetic"),
    # Mechanical
    "DIAGNOSTIC TROUBLE CODES":          ("mechanical", "diagnostic_trouble_codes"),
    "EMISSIONS/CATALYTIC/EXHAUST":       ("mechanical", "emissions_catalytic"),
    "ENGINE NOISE":                      ("mechanical", "engine_noise"),
    "WARNING LIGHTS & GAUGE CLUSTER":    ("mechanical", "warning_lights"),
    "ACTIVE VISIBLE LEAKS FROM ENGINE OR UNDERCARRIAGE AREA": ("mechanical", "active_visible_leaks"),
    "ENGINE OIL SLUDGE":                 ("mechanical", "engine_oil_sludge"),
    "VEHICLE SMOKE":                     ("mechanical", "vehicle_smoke"),
    "OTHER MECHANICAL COMMENTS":         ("mechanical", "other_mechanical"),
    # Tires
    "DRIVER FRONT TIRE DEPTH":           ("tires", "driver_front_tire_depth"),
    "DRIVER FRONT TIRE & WHEEL ISSUE":   ("tires", "driver_front_tire_issue"),
    "DRIVER REAR TIRE DEPTH":            ("tires", "driver_rear_tire_depth"),
    "DRIVER REAR TIRE & WHEEL ISSUE":    ("tires", "driver_rear_tire_issue"),
    "PASSENGER FRONT TIRE DEPTH":        ("tires", "passenger_front_tire_depth"),
    "PASSENGER FRONT TIRE & WHEEL ISSUE": ("tires", "passenger_front_tire_issue"),
    "PASSENGER REAR TIRE DEPTH":         ("tires", "passenger_rear_tire_depth"),
    "PASSENGER REAR TIRE & WHEEL ISSUE": ("tires", "passenger_rear_tire_issue"),
}


def _parse_body_text_inspection(report: dict[str, Any]) -> dict[str, Any] | None:
    """Extract all NAAA inspection fields from the CR page body_text.

    The body_text is a plain-text rendering of the Manheim inspection page.
    Each NAAA field appears as an ALL-CAPS label on one line followed by its
    value on the next line.  This parser scans for known labels and captures
    the value that follows.
    """
    metadata = report.get("metadata")
    if not isinstance(metadata, dict):
        return None
    report_page = metadata.get("report_page")
    if not isinstance(report_page, dict):
        return None
    body_text = report_page.get("body_text")
    if not isinstance(body_text, str) or len(body_text) < 50:
        return None

    lines = [line.strip() for line in body_text.splitlines()]
    result: dict[str, dict[str, str]] = {}

    i = 0
    while i < len(lines) - 1:
        label = lines[i].upper().strip()
        if label in _BODY_TEXT_FIELD_MAP:
            section_id, field_id = _BODY_TEXT_FIELD_MAP[label]
            value = lines[i + 1].strip()
            # Guard against capturing the next label as a value
            if value.upper() not in _BODY_TEXT_FIELD_MAP and value:
                result.setdefault(section_id, {})[field_id] = value
                i += 2
                continue
        i += 1

    return result if result else None


def _condition_report_has_content(value: dict[str, Any]) -> bool:
    for item in value.values():
        if item not in (None, "", [], {}):
            return True
    return False


def _normalize_autocheck(raw_ac: dict[str, Any], *, from_ove_listing: bool = False) -> dict[str, Any]:
    """Map scraper/OVE AutoCheck data to the schema the frontend expects."""
    def _check_text(ok: bool | None, label: str) -> str | None:
        if ok is True:
            return f"No {label} reported"
        if ok is False:
            return f"{label} information reported"
        return None

    accident_count = _first_coerce_int(
        raw_ac.get("accident_count"),
        raw_ac.get("numberOfAccidents"),
        raw_ac.get("number_of_accidents"),
    )
    owner_count = _first_coerce_int(
        raw_ac.get("owner_count"),
        raw_ac.get("ownerCount"),
        raw_ac.get("calculatedOwners"),
    )
    if accident_count is None:
        normalized_accident_check = None
    elif accident_count == 0:
        normalized_accident_check = "OK"
    else:
        normalized_accident_check = f"Information Reported({accident_count})"

    vehicle_use_ok = _coerce_bool(raw_ac.get("vehicleUseAndEventCheckOK"))
    normalized_vehicle_use = None
    if vehicle_use_ok is True:
        normalized_vehicle_use = "OK"
    elif vehicle_use_ok is False:
        normalized_vehicle_use = "Other Use Reported"

    normalized: dict[str, Any] = {
        "scrape_status": _first_clean_text(raw_ac.get("scrape_status"), raw_ac.get("status")) or "success",
        "attempted_at": _first_clean_text(raw_ac.get("attempted_at"), raw_ac.get("captured_at"), raw_ac.get("scraped_at")),
        "autocheck_score": _first_coerce_int(raw_ac.get("autocheck_score"), raw_ac.get("score")),
        "score_range_low": _first_coerce_int(
            raw_ac.get("score_range_low"),
            raw_ac.get("scoreRangeLow"),
            raw_ac.get("score_min"),
            raw_ac.get("scoreMin"),
            raw_ac.get("low_score"),
        ),
        "score_range_high": _first_coerce_int(
            raw_ac.get("score_range_high"),
            raw_ac.get("scoreRangeHigh"),
            raw_ac.get("score_max"),
            raw_ac.get("scoreMax"),
            raw_ac.get("high_score"),
        ),
        "score_range_label": _first_clean_text(
            raw_ac.get("score_range_label"),
            raw_ac.get("scoreRangeLabel"),
            raw_ac.get("comparison_class"),
            raw_ac.get("vehicleClass"),
        ),
        "historical_event_count": _first_coerce_int(
            raw_ac.get("historical_event_count"),
            raw_ac.get("historical_events"),
            raw_ac.get("event_count"),
            raw_ac.get("number_of_historical_events"),
            raw_ac.get("numberOfHistoricalEvents"),
        ),
        "owner_count": owner_count,
        "accident_count": accident_count,
        "last_reported_event_date": _first_clean_text(
            raw_ac.get("last_reported_event_date"),
            raw_ac.get("last_event_date"),
            raw_ac.get("lastReportedEventDate"),
        ),
        "last_reported_mileage": _first_coerce_int(
            raw_ac.get("last_reported_mileage"),
            raw_ac.get("last_reported_odometer"),
            raw_ac.get("last_mileage"),
            raw_ac.get("lastReportedMileage"),
        ),
        "title_brand_check": _first_clean_text(raw_ac.get("title_brand_check"))
        or _check_text(_coerce_bool(raw_ac.get("titleAndProblemCheckOK")), "title brand issues"),
        "odometer_check": _first_clean_text(raw_ac.get("odometer_check"))
        or _check_text(_coerce_bool(raw_ac.get("odometerCheckOK")), "odometer problems"),
        "accident_check": _first_clean_text(raw_ac.get("accident_check"))
        or normalized_accident_check,
        "damage_check": _first_clean_text(raw_ac.get("damage_check"))
        or _check_text(_coerce_bool(raw_ac.get("damageCheckOK")), "damage"),
        "other_title_brand_event_check": _first_clean_text(
            raw_ac.get("other_title_brand_event_check"),
            raw_ac.get("otherTitleBrandEventCheck"),
        ),
        "vehicle_use": _first_clean_text(raw_ac.get("vehicle_use"))
        or normalized_vehicle_use,
        "buyback_protection": _first_clean_text(
            raw_ac.get("buyback_protection"),
            raw_ac.get("buybackProtection"),
        ),
        "report_logo_url": _first_clean_text(raw_ac.get("report_logo_url"), raw_ac.get("logoUrl")),
        "view_report_href": _first_clean_text(
            raw_ac.get("view_report_href"),
            raw_ac.get("reportUrl"),
            raw_ac.get("report_url"),
            raw_ac.get("href"),
        ),
        "full_report_text": _first_clean_text(raw_ac.get("full_report_text"), raw_ac.get("transcript")),
        "failure_category": _first_clean_text(raw_ac.get("failure_category")),
        "failure_message": _first_clean_text(raw_ac.get("failure_message"), raw_ac.get("message")),
    }
    if from_ove_listing and not normalized["other_title_brand_event_check"]:
        normalized["other_title_brand_event_check"] = normalized["title_brand_check"]

    return {key: value for key, value in normalized.items() if value not in (None, "", [], {})}


def _normalize_ove_autocheck(ove_ac: dict[str, Any]) -> dict[str, Any]:
    """Map OVE's autocheck block to the schema the frontend expects."""
    return _normalize_autocheck(ove_ac, from_ove_listing=True)


def _normalize_condition_report_payload(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValueError("condition_report must be an object")

    # Short-circuit: if the original payload has no meaningful CR content,
    # return empty immediately.  This prevents downstream enrichment steps
    # (inspection, granular_inspection) from synthesizing keys that would
    # make _condition_report_has_content() return True and trigger full
    # field validation — which would fail for not-found/unavailable VINs.
    if not _condition_report_has_content(value):
        return {}

    report = dict(value)

    overall_grade = _clean_text(report.get("overall_grade")) or _clean_text(report.get("grade"))

    had_direct_announcements = "announcements" in report
    metadata_raw = report.get("metadata")
    metadata = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}

    report_link_raw = metadata.get("report_link")
    report_link = dict(report_link_raw) if isinstance(report_link_raw, dict) else {}

    # The OVE report_link block carries the true CR grade in valueText (e.g. "5",
    # "4.2").  The scraper sometimes sets overall_grade to the arbitration rating
    # (an integer 1-5 that means something different).  Prefer valueText when it
    # looks like a CR grade so the report shows the correct number.
    value_text_grade = _clean_text(report_link.get("valueText"))
    if value_text_grade and overall_grade and value_text_grade != overall_grade:
        overall_grade = value_text_grade
    elif not overall_grade and value_text_grade:
        overall_grade = value_text_grade

    if overall_grade:
        report["overall_grade"] = overall_grade

    legacy_report_url = _clean_text(report.get("condition_report_url")) or _clean_text(report.get("report_link"))
    href = _clean_text(report_link.get("href")) or legacy_report_url
    title = _clean_text(report_link.get("title")) or overall_grade
    if href:
        report_link["href"] = href
    if title:
        report_link["title"] = title
    if report_link:
        metadata["report_link"] = report_link

    announcements_enrichment_raw = metadata.get("announcementsEnrichment")
    announcements_enrichment = (
        dict(announcements_enrichment_raw)
        if isinstance(announcements_enrichment_raw, dict)
        else {}
    )
    had_meta_announcements = "announcements" in announcements_enrichment
    metadata_announcements = _clean_str_list(
        announcements_enrichment.get("announcements"),
        max_item_chars=400,
    )
    direct_announcements = _clean_str_list(report.get("announcements"), max_item_chars=400)
    if direct_announcements:
        report["announcements"] = direct_announcements
    elif metadata_announcements:
        report["announcements"] = metadata_announcements
    elif had_direct_announcements:
        report["announcements"] = []
    if metadata_announcements or had_meta_announcements:
        announcements_enrichment["announcements"] = metadata_announcements
    if announcements_enrichment:
        metadata["announcementsEnrichment"] = announcements_enrichment

    scrape_warnings = _clean_str_list(metadata.get("scrape_warnings"))
    if scrape_warnings:
        metadata["scrape_warnings"] = scrape_warnings
    if metadata:
        report["metadata"] = metadata

    for key in ("remarks", "seller_comments_items", "problem_highlights"):
        cleaned = _clean_str_list(report.get(key))
        if cleaned:
            report[key] = cleaned
        else:
            report.pop(key, None)

    equipment_features = _clean_str_list(report.get("equipment_features"))
    if equipment_features:
        report["equipment_features"] = equipment_features
    elif "equipment_features" in report:
        report["equipment_features"] = []

    for key in ("installed_equipment", "high_value_options"):
        raw_items = report.get(key)
        if not isinstance(raw_items, list):
            if key in report:
                report[key] = []
            continue
        normalized_items: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            normalized_items.append(
                {
                    str(inner_key): inner_value
                    for inner_key, inner_value in item.items()
                    if inner_value not in (None, "")
                }
            )
        report[key] = normalized_items

    ai_summary = _clean_text(report.get("ai_summary"))
    if ai_summary:
        report["ai_summary"] = ai_summary

    severity_summary = _clean_text(report.get("severity_summary"))
    if severity_summary:
        report["severity_summary"] = severity_summary

    raw_text = _clean_text(report.get("raw_text"))
    if raw_text:
        report["raw_text"] = raw_text[:16_000]

    for key in (
        "structural_damage",
        "paint_condition",
        "interior_condition",
        "tire_condition",
        "title_status",
        "title_state",
        "title_branding",
        "exterior_color",
        "interior_color",
    ):
        cleaned = _clean_text(report.get(key))
        if cleaned:
            report[key] = cleaned
        else:
            report.pop(key, None)

    vehicle_history_raw = report.get("vehicle_history")
    if vehicle_history_raw is not None:
        if not isinstance(vehicle_history_raw, dict):
            raise ValueError("condition_report.vehicle_history must be an object")
        vehicle_history = dict(vehicle_history_raw)
        owners = _coerce_int(vehicle_history.get("owners"))
        accidents = _coerce_int(vehicle_history.get("accidents"))
        engine_starts = _coerce_bool(vehicle_history.get("engine_starts"))
        drivable = _coerce_bool(vehicle_history.get("drivable"))
        normalized_history: dict[str, Any] = {}
        if owners is not None:
            normalized_history["owners"] = owners
        if accidents is not None:
            normalized_history["accidents"] = accidents
        if engine_starts is not None:
            normalized_history["engine_starts"] = engine_starts
        if drivable is not None:
            normalized_history["drivable"] = drivable
        if normalized_history:
            report["vehicle_history"] = normalized_history
        else:
            report.pop("vehicle_history", None)

    damage_items_raw = report.get("damage_items")
    if damage_items_raw is not None:
        if not isinstance(damage_items_raw, list):
            raise ValueError("condition_report.damage_items must be an array")
        normalized_damage_items: list[dict[str, Any]] = []
        for item in damage_items_raw:
            if not isinstance(item, dict):
                continue
            cleaned = {str(key): value for key, value in item.items() if value not in (None, "")}
            normalized_damage_items.append(cleaned)
        report["damage_items"] = normalized_damage_items

    damage_summary_raw = report.get("damage_summary")
    if damage_summary_raw is not None:
        if not isinstance(damage_summary_raw, dict):
            raise ValueError("condition_report.damage_summary must be an object")
        damage_summary = {
            str(key): value for key, value in damage_summary_raw.items() if value not in (None, "")
        }
        if damage_summary:
            report["damage_summary"] = damage_summary
        else:
            report.pop("damage_summary", None)

    tire_depths_raw = report.get("tire_depths")
    if tire_depths_raw is not None:
        if not isinstance(tire_depths_raw, dict):
            raise ValueError("condition_report.tire_depths must be an object")
        normalized_tire_depths: dict[str, dict[str, Any]] = {}
        for position, item in tire_depths_raw.items():
            key = _clean_text(position)
            if not key or not isinstance(item, dict):
                continue
            normalized_position = key.lower()
            cleaned_item = {
                str(inner_key): inner_value
                for inner_key, inner_value in item.items()
                if inner_value not in (None, "")
            }
            if cleaned_item:
                normalized_tire_depths[normalized_position] = cleaned_item
        if normalized_tire_depths:
            report["tire_depths"] = normalized_tire_depths
        else:
            report.pop("tire_depths", None)

    autocheck_raw = report.get("autocheck")
    if autocheck_raw is not None:
        if not isinstance(autocheck_raw, dict):
            raise ValueError("condition_report.autocheck must be an object")
        autocheck = _normalize_autocheck(autocheck_raw)
        if autocheck:
            report["autocheck"] = autocheck
        else:
            report.pop("autocheck", None)

    # Extract AutoCheck from OVE listing_json when the scraper didn't provide
    # a top-level autocheck block.  OVE stores it under metadata.listing_json.autocheck.
    if not report.get("autocheck"):
        listing_json = metadata.get("listing_json")
        if isinstance(listing_json, dict):
            ove_ac = listing_json.get("autocheck")
            if isinstance(ove_ac, dict):
                report["autocheck"] = _normalize_ove_autocheck(ove_ac)

    # Surface tire issues (e.g. "Wheel Cosmetic Damage") as problem highlights
    # so they are visible in the damage/highlights section of the report.
    tire_depths_for_issues = report.get("tire_depths")
    if isinstance(tire_depths_for_issues, dict):
        existing_highlights = report.get("problem_highlights") or []
        existing_set = {h.lower() for h in existing_highlights}
        for pos_key, tire in tire_depths_for_issues.items():
            if not isinstance(tire, dict):
                continue
            issue = _clean_text(tire.get("issue"))
            if issue and issue.lower() not in ("no issues", "none", "n/a", ""):
                label = _clean_text(tire.get("position_label")) or pos_key.replace("_", " ").title()
                highlight = f"{label}: {issue}"
                if highlight.lower() not in existing_set:
                    existing_highlights.append(highlight)
                    existing_set.add(highlight.lower())
        if existing_highlights:
            report["problem_highlights"] = existing_highlights

    # Build the NAAA inspection dict — always fully populated.
    report["inspection"] = _normalize_inspection(
        report.get("inspection"),
        report,
    )

    granular = normalize_granular_condition_report(report.get("granular_inspection"))
    report["granular_inspection"] = granular or build_granular_condition_report(report)

    if not _condition_report_has_content(report):
        return {}

    validation_errors: list[str] = []
    if not overall_grade:
        validation_errors.append("condition_report.overall_grade is required")

    normalized_metadata = report.get("metadata") or {}
    normalized_report_link = normalized_metadata.get("report_link") or {}
    if not _clean_text(normalized_report_link.get("href")):
        validation_errors.append("condition_report.metadata.report_link.href is required")

    has_direct_announcements = "announcements" in report
    has_meta_announcements = "announcements" in (normalized_metadata.get("announcementsEnrichment") or {})
    if not has_direct_announcements and not has_meta_announcements:
        validation_errors.append(
            "condition_report.announcements or condition_report.metadata.announcementsEnrichment.announcements is required"
        )

    normalized_history = report.get("vehicle_history") or {}
    if _coerce_int(normalized_history.get("owners")) is None or _coerce_int(normalized_history.get("accidents")) is None:
        validation_errors.append("condition_report.vehicle_history.owners and .accidents are required")

    if "damage_items" not in report:
        validation_errors.append("condition_report.damage_items is required")

    tire_depths = report.get("tire_depths")
    required_tire_positions = {"lf", "rf", "lr", "rr"}
    if not isinstance(tire_depths, dict) or not required_tire_positions.issubset(set(tire_depths.keys())):
        validation_errors.append("condition_report.tire_depths must include lf, rf, lr, and rr")

    if validation_errors:
        raise ValueError("; ".join(validation_errors))

    return report


class OveVehicleIngestItem(BaseModel):
    vin: str
    listing_id: str | None = None
    year: int
    make: str
    model: str
    trim: str | None = None
    body_type: str | None = None
    sub_body_type: str | None = None
    engine_type: str | None = None
    cylinders: int | None = None
    forced_induction: str | None = None
    drivetrain: str | None = None
    mpg_combined: float | None = None
    ev_range: int | None = None
    towing_capacity_lbs: int | None = None
    odometer: int | None = None
    odometer_units: str | None = None
    condition_grade: str | None = None
    exterior_color: str | None = None
    interior_color: str | None = None
    transmission_type: str | None = None
    fuel_type: str | None = None
    pickup_location: str | None = None
    price_asking: float
    price_wholesale_est: float | None = None
    location_zip: str | None = None
    location_state: str | None = None
    source_url: str | None = None
    source_type: InventorySourceType = InventorySourceType.OVE
    source_platform: AuctionPlatform = AuctionPlatform.MANHEIM
    images: list[str] = Field(default_factory=list)
    features_raw: list[str] = Field(default_factory=list)
    features_normalized: dict[str, Any] = Field(default_factory=dict)
    available: bool = True
    quality_firewall_pass: bool | None = True

    @field_validator("vin")
    @classmethod
    def validate_vin(cls, value: str) -> str:
        return _normalize_vin(value)

    @field_validator("location_state")
    @classmethod
    def normalize_state(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip().upper()
        return text[:2] or None

    @field_validator("images")
    @classmethod
    def normalize_images(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if str(item).strip()]

    @field_validator("source_type")
    @classmethod
    def require_ove_source(cls, value: InventorySourceType) -> InventorySourceType:
        if value != InventorySourceType.OVE:
            raise ValueError("source_type must be 'ove'")
        return value


class OveBulkIngestRequest(BaseModel):
    vehicles: list[OveVehicleIngestItem] = Field(default_factory=list)
    sync_metadata: dict[str, Any] = Field(default_factory=dict)


class OveBulkIngestResponse(BaseModel):
    source: InventorySourceType = InventorySourceType.OVE
    source_platforms: list[AuctionPlatform] = Field(default_factory=list)
    requested: int
    inserted: int
    updated: int
    skipped_priority: int
    skipped_invalid: int
    synced_vins: list[str] = Field(default_factory=list)
    sync_metadata: dict[str, Any] = Field(default_factory=dict)


class OveImagePayload(BaseModel):
    url: str
    role: str = "gallery"
    category: str = "all"  # all | ext | int | misc | dmg | video
    display_order: int = 0
    is_primary: bool = False
    source_image_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def normalize_url(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("image url is required")
        return cleaned


class OveListingSnapshotSection(BaseModel):
    id: str | None = None
    title: str | None = None
    subtitle: str | None = None
    layout: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class OveListingSnapshot(BaseModel):
    title: str | None = None
    subtitle: str | None = None
    badges: list[dict[str, Any]] = Field(default_factory=list)
    hero_facts: list[dict[str, Any]] = Field(default_factory=list)
    sections: list[OveListingSnapshotSection] = Field(default_factory=list)
    icons: list[dict[str, Any]] = Field(default_factory=list)
    page_url: str | None = None
    screenshot_refs: list[str] = Field(default_factory=list)
    raw_html_ref: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OveDetailPushRequest(BaseModel):
    source_platform: AuctionPlatform = AuctionPlatform.MANHEIM
    images: list[OveImagePayload] = Field(default_factory=list)
    condition_report: dict[str, Any] = Field(default_factory=dict)
    seller_comments: str | None = None
    listing_snapshot: OveListingSnapshot = Field(default_factory=OveListingSnapshot)
    sync_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("condition_report", mode="before")
    @classmethod
    def normalize_condition_report(cls, value: Any) -> dict[str, Any]:
        return _normalize_condition_report_payload(value)

    @model_validator(mode="after")
    def validate_condition_report_images(self) -> "OveDetailPushRequest":
        if self.condition_report and not self.images:
            raise ValueError("images must include the OVE gallery when condition_report is present")
        return self


class OveDetailPushResponse(BaseModel):
    vin: str
    source_platform: AuctionPlatform
    detail_saved: bool = True
    images_synced: int = 0
    hero_job_queued: bool = False
    completed_request_ids: list[str] = Field(default_factory=list)
    seller_comments_present: bool = False
    listing_snapshot_present: bool = False
    condition_report_present: bool = False
    sync_metadata: dict[str, Any] = Field(default_factory=dict)


class OvePendingDetailRequestItem(BaseModel):
    request_id: str
    vin: str
    source_platform: AuctionPlatform
    status: OveDetailRequestStatus
    priority: int
    attempts: int
    requested_at: str
    last_polled_at: str | None = None
    request_source: str
    requested_by: str
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OvePendingDetailPollResponse(BaseModel):
    items: list[OvePendingDetailRequestItem] = Field(default_factory=list)
    count: int = 0


class OveDetailRequestEnqueueRequest(BaseModel):
    source_platform: AuctionPlatform = AuctionPlatform.MANHEIM
    priority: int = 100
    request_source: str = "api"
    requested_by: str = "system"
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OveDetailRequestEnqueueResponse(BaseModel):
    request_id: str
    vin: str
    source_platform: AuctionPlatform
    status: OveDetailRequestStatus
    deduplicated: bool = False
    priority: int
    requested_at: str
    request_source: str
    requested_by: str
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Lease-based claim queue contracts
# ---------------------------------------------------------------------------


class OveDetailClaimRequest(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=120)
    limit: int = Field(default=10, ge=1, le=100)
    lease_seconds: int = Field(default=900, ge=30, le=7200)


class OveDetailClaimedItem(BaseModel):
    request_id: str
    vin: str
    source_platform: AuctionPlatform
    priority: int
    attempts: int
    requested_at: str
    claimed_at: str
    lease_expires_at: str
    request_source: str
    requested_by: str
    reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OveDetailClaimResponse(BaseModel):
    worker_id: str
    lease_seconds: int
    items: list[OveDetailClaimedItem] = Field(default_factory=list)
    count: int = 0


class OveDetailCompleteRequest(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=120)
    result: str = "success"


class OveDetailFailRequest(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=120)
    error_category: str = Field(default="unknown", max_length=80)
    error_message: str | None = None
    retry_after_seconds: int = Field(default=600, ge=0, le=86_400)


class OveDetailTerminalRequest(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=120)
    reason: str = Field(..., min_length=1, max_length=120)
    message: str | None = None


class OveDetailHeartbeatRequest(BaseModel):
    worker_id: str = Field(..., min_length=1, max_length=120)
    lease_seconds: int = Field(default=900, ge=30, le=7200)


class OveScraperHeartbeatRequest(BaseModel):
    """Liveness signal from a scraper worker. All fields other than
    worker_id are optional — callers send whichever values they currently
    know and the server upserts only the provided fields so a partial
    heartbeat never clobbers richer state from an earlier call.
    """

    worker_id: str = Field(..., min_length=1, max_length=120)
    profile: str | None = Field(default=None, max_length=120)
    scraper_version: str | None = Field(default=None, max_length=80)
    node_id: str | None = Field(default=None, max_length=120)
    last_sync_at: datetime | None = None
    last_poll_at: datetime | None = None
    last_claim_at: datetime | None = None
    pending_claims: int | None = Field(default=None, ge=0, le=100_000)
    status_note: str | None = Field(default=None, max_length=255)
    details: dict[str, Any] = Field(default_factory=dict)
