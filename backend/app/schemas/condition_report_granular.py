from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


NORMAL_DAMAGE_VALUE = "Normal - No Damage Reported"
NORMAL_ISSUE_VALUE = "Normal - No Issue Reported"


GRANULAR_SECTION_DEFS: dict[str, dict[str, Any]] = {
    "drivability": {
        "label": "Drivability, Keys, & History",
        "default": NORMAL_ISSUE_VALUE,
        "fields": {
            "vehicle_drives": "Vehicle Drives",
            "vehicle_starts": "Vehicle Starts",
            "smart_keys": "Smart Keys",
            "other_keys": "Other Keys",
            "odor_bio": "Odor/Bio/Environmental/History",
        },
    },
    "exterior": {
        "label": "Exterior",
        "default": NORMAL_DAMAGE_VALUE,
        "groups": {
            "top_ends": "Top & Ends",
            "mirrors": "Mirrors",
            "driver_side": "Driver Side",
            "passenger_side": "Passenger Side",
            "other": "Other",
        },
        "fields": {
            "front_bumper": "Front Bumper",
            "hood": "Hood",
            "roof": "Roof",
            "trunk_liftgate": "Trunk / Liftgate",
            "rear_bumper": "Rear Bumper",
            "driver_mirror": "Driver Mirror",
            "passenger_mirror": "Passenger Mirror",
            "driver_fender": "Driver Fender",
            "driver_front_door": "Driver Front Door",
            "driver_rear_door": "Driver Rear Door",
            "driver_quarter": "Driver Quarter Panel",
            "passenger_fender": "Passenger Fender",
            "passenger_front_door": "Passenger Front Door",
            "passenger_rear_door": "Passenger Rear Door",
            "passenger_quarter": "Passenger Quarter Panel",
            "further_disclosures": "Further Disclosures",
        },
    },
    "interior": {
        "label": "Interior",
        "default": NORMAL_DAMAGE_VALUE,
        "groups": {
            "seats": "Cosmetic Damage - Seats",
            "door_panels": "Cosmetic Damage - Door Panels",
            "dashboard": "Cosmetic Damage - Dashboard & Headliner",
            "operation": "Operation & Equipment",
        },
        "fields": {
            "driver_seat": "Driver Seat",
            "passenger_seat": "Passenger Seat",
            "rear_left_seat": "Rear Left Seat",
            "rear_center_seat": "Rear Seat Center",
            "rear_right_seat": "Rear Right Seat",
            "third_row_seats": "Third Row Seats",
            "driver_door_panel": "Driver Door Panel",
            "passenger_door_panel": "Passenger Door Panel",
            "driver_rear_door_panel": "Driver Rear Door Panel",
            "passenger_rear_door_panel": "Passenger Rear Door Panel",
            "dashboard": "Dashboard",
            "headliner": "Headliner / Roof Liner",
            "airbags": "Airbags",
            "climate_control": "Climate Control",
            "electrical_accessory": "Electrical Accessory",
            "infotainment_radio": "Infotainment / Radio",
            "sunroof_operation": "Sunroof Operation",
            "smoke_odor": "Smoke Odor",
        },
    },
    "mechanical": {
        "label": "Mechanical & Diagnostic Trouble Codes",
        "default": NORMAL_ISSUE_VALUE,
        "fields": {
            "diagnostic_trouble_codes": "Diagnostic Trouble Codes",
            "emissions_catalytic": "Emissions / Catalytic / Exhaust",
            "engine_noise": "Engine Noise",
            "warning_lights": "Warning Lights & Gauge Cluster",
            "active_visible_leaks": "Active Visible Leaks",
            "engine_oil_sludge": "Engine Oil Sludge",
            "vehicle_smoke": "Vehicle Smoke",
            "other_mechanical": "Other Mechanical Comments",
        },
    },
    "tires": {
        "label": "Tires & Wheels",
        "default": NORMAL_ISSUE_VALUE,
        "fields": {
            "driver_front_tire_depth": "Driver Front Tire Depth",
            "driver_front_tire_issue": "Driver Front Tire & Wheel Issue",
            "driver_rear_tire_depth": "Driver Rear Tire Depth",
            "driver_rear_tire_issue": "Driver Rear Tire & Wheel Issue",
            "passenger_front_tire_depth": "Passenger Front Tire Depth",
            "passenger_front_tire_issue": "Passenger Front Tire & Wheel Issue",
            "passenger_rear_tire_depth": "Passenger Rear Tire Depth",
            "passenger_rear_tire_issue": "Passenger Rear Tire & Wheel Issue",
        },
    },
}


FIELD_GROUPS: dict[str, dict[str, str]] = {
    "exterior": {
        "front_bumper": "top_ends",
        "hood": "top_ends",
        "roof": "top_ends",
        "trunk_liftgate": "top_ends",
        "rear_bumper": "top_ends",
        "driver_mirror": "mirrors",
        "passenger_mirror": "mirrors",
        "driver_fender": "driver_side",
        "driver_front_door": "driver_side",
        "driver_rear_door": "driver_side",
        "driver_quarter": "driver_side",
        "passenger_fender": "passenger_side",
        "passenger_front_door": "passenger_side",
        "passenger_rear_door": "passenger_side",
        "passenger_quarter": "passenger_side",
        "further_disclosures": "other",
    },
    "interior": {
        "driver_seat": "seats",
        "passenger_seat": "seats",
        "rear_left_seat": "seats",
        "rear_center_seat": "seats",
        "rear_right_seat": "seats",
        "third_row_seats": "seats",
        "driver_door_panel": "door_panels",
        "passenger_door_panel": "door_panels",
        "driver_rear_door_panel": "door_panels",
        "passenger_rear_door_panel": "door_panels",
        "dashboard": "dashboard",
        "headliner": "dashboard",
        "airbags": "operation",
        "climate_control": "operation",
        "electrical_accessory": "operation",
        "infotainment_radio": "operation",
        "sunroof_operation": "operation",
        "smoke_odor": "operation",
    },
}


_CLEAN_VALUE_RE = re.compile(
    r"\b(no issues?|none|no damage|normal|ok|not inspected|not specified|not applicable|n/a|yes - starts|yes - drives)\b",
    re.I,
)

_REPAIRED_SECTION_RE = re.compile(r"\brepaired\b", re.I)
_REPAIR_STATUS_VALUES = frozenset({"repaired", "completed", "done", "approved"})


_FIELD_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    # Manheim two-letter abbreviation + panel patterns (must precede general patterns;
    # tire patterns further below require tire/wheel/rim/curb so there is no collision).
    ("exterior", "front_bumper", re.compile(r"\b[lr]f\b.*\bbumper\b|\bbumper\b.*\b[lr]f\b", re.I)),
    ("exterior", "rear_bumper", re.compile(r"\b[lr]r\b.*\bbumper\b|\bbumper\b.*\b[lr]r\b", re.I)),
    ("exterior", "driver_front_door", re.compile(r"\blf\b.*\bdoor\b|\bdoor\b.*\blf\b", re.I)),
    ("exterior", "driver_rear_door", re.compile(r"\blr\b.*\bdoor\b|\bdoor\b.*\blr\b", re.I)),
    ("exterior", "passenger_front_door", re.compile(r"\brf\b.*\bdoor\b|\bdoor\b.*\brf\b", re.I)),
    ("exterior", "passenger_rear_door", re.compile(r"\brr\b.*\bdoor\b|\bdoor\b.*\brr\b", re.I)),
    ("exterior", "driver_fender", re.compile(r"\blf\b.*\bfender\b|\bfender\b.*\blf\b", re.I)),
    ("exterior", "passenger_fender", re.compile(r"\brf\b.*\bfender\b|\bfender\b.*\brf\b", re.I)),
    ("exterior", "driver_quarter", re.compile(r"\blr\b.*\bquarter\b|\bquarter\b.*\blr\b", re.I)),
    ("exterior", "passenger_quarter", re.compile(r"\brr\b.*\bquarter\b|\bquarter\b.*\brr\b", re.I)),
    # General panel patterns
    ("exterior", "front_bumper", re.compile(r"\b(front|frt)\s+bumper\b|\bbumper\b.*\bfront\b", re.I)),
    ("exterior", "rear_bumper", re.compile(r"\b(rear|back)\s+bumper\b|\bbumper\b.*\brear\b", re.I)),
    ("exterior", "hood", re.compile(r"\bhood\b", re.I)),
    ("exterior", "roof", re.compile(r"\broof\b", re.I)),
    ("exterior", "trunk_liftgate", re.compile(r"\b(trunk|liftgate|tailgate|hatch)\b", re.I)),
    ("exterior", "driver_mirror", re.compile(r"\b(driver|left|lh)\b.*\bmirror\b|\bmirror\b.*\b(driver|left|lh)\b", re.I)),
    ("exterior", "passenger_mirror", re.compile(r"\b(passenger|right|rh)\b.*\bmirror\b|\bmirror\b.*\b(passenger|right|rh)\b", re.I)),
    ("exterior", "driver_fender", re.compile(r"\b(driver|left|lh)\b.*\bfender\b|\bfender\b.*\b(driver|left|lh)\b", re.I)),
    ("exterior", "passenger_fender", re.compile(r"\b(passenger|right|rh)\b.*\bfender\b|\bfender\b.*\b(passenger|right|rh)\b", re.I)),
    ("exterior", "driver_front_door", re.compile(r"\b(driver|left|lh)\b.*\bfront\b.*\bdoor\b|\bfront\b.*\b(driver|left|lh)\b.*\bdoor\b", re.I)),
    ("exterior", "driver_rear_door", re.compile(r"\b(driver|left|lh)\b.*\b(rear|back)\b.*\bdoor\b|\b(rear|back)\b.*\b(driver|left|lh)\b.*\bdoor\b", re.I)),
    ("exterior", "passenger_front_door", re.compile(r"\b(passenger|right|rh)\b.*\bfront\b.*\bdoor\b|\bfront\b.*\b(passenger|right|rh)\b.*\bdoor\b", re.I)),
    ("exterior", "passenger_rear_door", re.compile(r"\b(passenger|right|rh)\b.*\b(rear|back)\b.*\bdoor\b|\b(rear|back)\b.*\b(passenger|right|rh)\b.*\bdoor\b", re.I)),
    ("exterior", "driver_quarter", re.compile(r"\b(driver|left|lh)\b.*\bquarter\b|\bquarter\b.*\b(driver|left|lh)\b", re.I)),
    ("exterior", "passenger_quarter", re.compile(r"\b(passenger|right|rh)\b.*\bquarter\b|\bquarter\b.*\b(passenger|right|rh)\b", re.I)),
    ("interior", "driver_rear_door_panel", re.compile(r"\b(driver|left|lh)\b.*\b(rear|back)\b.*\b(door panel|arm ?rest|trim)\b|\b(rear|back)\b.*\b(driver|left|lh)\b.*\b(door panel|arm ?rest|trim)\b", re.I)),
    ("interior", "passenger_rear_door_panel", re.compile(r"\b(passenger|right|rh)\b.*\b(rear|back)\b.*\b(door panel|arm ?rest|trim)\b|\b(rear|back)\b.*\b(passenger|right|rh)\b.*\b(door panel|arm ?rest|trim)\b", re.I)),
    ("interior", "driver_door_panel", re.compile(r"\b(driver|left|lh)\b.*\b(door panel|arm ?rest|trim)\b|\b(door panel|arm ?rest|trim)\b.*\b(driver|left|lh)\b", re.I)),
    ("interior", "passenger_door_panel", re.compile(r"\b(passenger|right|rh)\b.*\b(door panel|arm ?rest|trim)\b|\b(door panel|arm ?rest|trim)\b.*\b(passenger|right|rh)\b", re.I)),
    ("interior", "driver_seat", re.compile(r"\b(driver|left|lh)\b.*\bseat\b|\bseat\b.*\b(driver|left|lh)\b", re.I)),
    ("interior", "passenger_seat", re.compile(r"\b(passenger|right|rh)\b.*\bseat\b|\bseat\b.*\b(passenger|right|rh)\b", re.I)),
    ("interior", "rear_left_seat", re.compile(r"\brear\b.*\b(left|driver|lh)\b.*\bseat\b", re.I)),
    ("interior", "rear_right_seat", re.compile(r"\brear\b.*\b(right|passenger|rh)\b.*\bseat\b", re.I)),
    ("interior", "rear_center_seat", re.compile(r"\brear\b.*\b(center|middle)\b.*\bseat\b", re.I)),
    ("interior", "third_row_seats", re.compile(r"\bthird row\b.*\bseat\b", re.I)),
    ("interior", "dashboard", re.compile(r"\b(dash|dashboard)\b", re.I)),
    ("interior", "headliner", re.compile(r"\b(headliner|roof liner)\b", re.I)),
    ("interior", "smoke_odor", re.compile(r"\b(smoke|odor|odour)\b", re.I)),
    ("mechanical", "warning_lights", re.compile(r"\b(warning light|check engine|abs light|airbag light|gauge cluster)\b", re.I)),
    ("mechanical", "active_visible_leaks", re.compile(r"\b(leak|leaking|oil leak|fluid leak)\b", re.I)),
    ("mechanical", "engine_noise", re.compile(r"\b(engine noise|tick|knock|rattle)\b", re.I)),
    ("mechanical", "diagnostic_trouble_codes", re.compile(r"\b(dtc|diagnostic trouble|code[s]?|scan)\b", re.I)),
    ("mechanical", "vehicle_smoke", re.compile(r"\b(smoke from|vehicle smoke|exhaust smoke)\b", re.I)),
    ("tires", "driver_front_tire_issue", re.compile(r"\b(lf|left front|driver front)\b.*\b(tire|wheel|rim|curb)\b", re.I)),
    ("tires", "passenger_front_tire_issue", re.compile(r"\b(rf|right front|passenger front)\b.*\b(tire|wheel|rim|curb)\b", re.I)),
    ("tires", "driver_rear_tire_issue", re.compile(r"\b(lr|left rear|driver rear)\b.*\b(tire|wheel|rim|curb)\b", re.I)),
    ("tires", "passenger_rear_tire_issue", re.compile(r"\b(rr|right rear|passenger rear)\b.*\b(tire|wheel|rim|curb)\b", re.I)),
]


_BROAD_INSPECTION_MAP: dict[tuple[str, str], tuple[str, str]] = {
    ("drivability", "vehicle_drives"): ("drivability", "vehicle_drives"),
    ("drivability", "vehicle_starts"): ("drivability", "vehicle_starts"),
    ("drivability", "smart_keys"): ("drivability", "smart_keys"),
    ("drivability", "other_keys"): ("drivability", "other_keys"),
    ("drivability", "odor_bio"): ("drivability", "odor_bio"),
    ("exterior", "front_exterior"): ("exterior", "front_bumper"),
    ("exterior", "driver_exterior"): ("exterior", "driver_front_door"),
    ("exterior", "roof_exterior"): ("exterior", "roof"),
    ("exterior", "passenger_exterior"): ("exterior", "passenger_front_door"),
    ("exterior", "rear_exterior"): ("exterior", "rear_bumper"),
    ("exterior", "further_disclosures"): ("exterior", "further_disclosures"),
    ("interior", "airbags"): ("interior", "airbags"),
    ("interior", "climate_control"): ("interior", "climate_control"),
    ("interior", "electrical_accessory"): ("interior", "electrical_accessory"),
    ("interior", "infotainment_radio"): ("interior", "infotainment_radio"),
    ("interior", "sunroof_operation"): ("interior", "sunroof_operation"),
    ("interior", "interior_cosmetic"): ("interior", "driver_seat"),
    ("mechanical", "diagnostic_trouble_codes"): ("mechanical", "diagnostic_trouble_codes"),
    ("mechanical", "emissions_catalytic"): ("mechanical", "emissions_catalytic"),
    ("mechanical", "engine_noise"): ("mechanical", "engine_noise"),
    ("mechanical", "warning_lights"): ("mechanical", "warning_lights"),
    ("mechanical", "active_visible_leaks"): ("mechanical", "active_visible_leaks"),
    ("mechanical", "engine_oil_sludge"): ("mechanical", "engine_oil_sludge"),
    ("mechanical", "vehicle_smoke"): ("mechanical", "vehicle_smoke"),
    ("mechanical", "other_mechanical"): ("mechanical", "other_mechanical"),
    ("tires", "driver_front_tire_depth"): ("tires", "driver_front_tire_depth"),
    ("tires", "driver_front_tire_issue"): ("tires", "driver_front_tire_issue"),
    ("tires", "driver_rear_tire_depth"): ("tires", "driver_rear_tire_depth"),
    ("tires", "driver_rear_tire_issue"): ("tires", "driver_rear_tire_issue"),
    ("tires", "passenger_front_tire_depth"): ("tires", "passenger_front_tire_depth"),
    ("tires", "passenger_front_tire_issue"): ("tires", "passenger_front_tire_issue"),
    ("tires", "passenger_rear_tire_depth"): ("tires", "passenger_rear_tire_depth"),
    ("tires", "passenger_rear_tire_issue"): ("tires", "passenger_rear_tire_issue"),
}


def build_granular_condition_report(report: dict[str, Any]) -> dict[str, Any]:
    granular = _empty_granular_report()
    repaired_panels = _extract_repaired_panels(report)
    _apply_structured_inspection(granular, report.get("inspection"))
    _apply_tire_depths(granular, report.get("tire_depths"))
    _apply_damage_items(granular, report.get("damage_items"), repaired_panels)
    _apply_text_sources(granular, report, repaired_panels)
    _refresh_issue_counts(granular)
    return granular


def normalize_granular_condition_report(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    granular = _empty_granular_report()
    for section_id, section in value.items():
        if section_id not in granular or not isinstance(section, dict):
            continue
        fields = section.get("fields")
        if not isinstance(fields, dict):
            continue
        for field_id, field in fields.items():
            if field_id not in granular[section_id]["fields"] or not isinstance(field, dict):
                continue
            merged = dict(granular[section_id]["fields"][field_id])
            status = str(field.get("status") or merged["status"]).strip().lower()
            if status not in {"normal", "issue", "unknown"}:
                status = merged["status"]
            merged["status"] = status
            for key in ("value", "source"):
                text = _clean_text(field.get(key))
                if text:
                    merged[key] = text
            confidence = _coerce_float(field.get("confidence"))
            if confidence is not None:
                merged["confidence"] = max(0.0, min(1.0, confidence))
            evidence = _clean_list(field.get("evidence"))
            if evidence:
                merged["evidence"] = evidence
            image_refs = _clean_list(field.get("image_refs"))
            if image_refs:
                merged["image_refs"] = image_refs
            granular[section_id]["fields"][field_id] = merged
    _refresh_issue_counts(granular)
    return granular


def apply_granular_ai_patches(
    report: dict[str, Any],
    patches: list[dict[str, Any]],
    *,
    auto_apply_confidence: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    granular = normalize_granular_condition_report(report.get("granular_inspection"))
    if granular is None:
        granular = build_granular_condition_report(report)

    accepted: list[dict[str, Any]] = []
    for patch in patches:
        if not isinstance(patch, dict):
            continue
        field_path = _clean_text(patch.get("field_path"))
        if not field_path or "." not in field_path:
            continue
        section_id, field_id = field_path.split(".", 1)
        if section_id not in granular or field_id not in granular[section_id]["fields"]:
            continue
        confidence = _coerce_float(patch.get("confidence")) or 0.0
        evidence = _clean_text(patch.get("evidence"))
        value = _clean_text(patch.get("value"))
        status = str(patch.get("status") or "issue").strip().lower()
        if status not in {"normal", "issue", "unknown"}:
            continue
        if confidence < auto_apply_confidence or (status == "issue" and not evidence):
            continue
        if not value:
            continue

        field = dict(granular[section_id]["fields"][field_id])
        field.update(
            {
                "status": status,
                "value": value,
                "source": "ai_review",
                "confidence": max(0.0, min(1.0, confidence)),
                "evidence": _merge_unique(field.get("evidence"), [evidence] if evidence else []),
            }
        )
        granular[section_id]["fields"][field_id] = field
        accepted.append(
            {
                "field_path": field_path,
                "status": status,
                "value": value,
                "evidence": evidence,
                "confidence": confidence,
                "reason": _clean_text(patch.get("reason")),
            }
        )

    _refresh_issue_counts(granular)
    updated = dict(report)
    updated["granular_inspection"] = granular
    return updated, accepted


def allowed_granular_field_paths() -> list[str]:
    paths: list[str] = []
    for section_id, section in GRANULAR_SECTION_DEFS.items():
        for field_id in section["fields"]:
            paths.append(f"{section_id}.{field_id}")
    return paths


def _empty_granular_report() -> dict[str, Any]:
    result: dict[str, Any] = {}
    for section_id, section_def in GRANULAR_SECTION_DEFS.items():
        default = section_def["default"]
        result[section_id] = {
            "label": section_def["label"],
            "issue_count": 0,
            "groups": deepcopy(section_def.get("groups", {})),
            "fields": {},
        }
        for field_id, label in section_def["fields"].items():
            result[section_id]["fields"][field_id] = {
                "label": label,
                "group": FIELD_GROUPS.get(section_id, {}).get(field_id),
                "status": "normal",
                "value": default,
                "source": "default",
                "confidence": 1.0,
                "evidence": [],
                "image_refs": [],
            }
    return result


def _apply_structured_inspection(granular: dict[str, Any], inspection: Any) -> None:
    if not isinstance(inspection, dict):
        return
    for src_section_id, src_section in inspection.items():
        if not isinstance(src_section, dict):
            continue
        fields = src_section.get("fields")
        if not isinstance(fields, dict):
            continue
        for src_field_id, src_field in fields.items():
            if not isinstance(src_field, dict):
                continue
            dest = _BROAD_INSPECTION_MAP.get((str(src_section_id), str(src_field_id)))
            if not dest:
                continue
            value = _clean_text(src_field.get("value"))
            if not value or _is_default_inspection_value(value, src_field):
                continue
            status = "issue" if bool(src_field.get("has_issue")) else "normal"
            _set_field(granular, dest[0], dest[1], status=status, value=value, source="inspection", evidence=value, confidence=0.9)


def _apply_tire_depths(granular: dict[str, Any], tire_depths: Any) -> None:
    if not isinstance(tire_depths, dict):
        return
    tire_map = {
        "lf": "driver_front",
        "left_front": "driver_front",
        "driver_front": "driver_front",
        "rf": "passenger_front",
        "right_front": "passenger_front",
        "passenger_front": "passenger_front",
        "lr": "driver_rear",
        "left_rear": "driver_rear",
        "driver_rear": "driver_rear",
        "rr": "passenger_rear",
        "right_rear": "passenger_rear",
        "passenger_rear": "passenger_rear",
    }
    for raw_pos, item in tire_depths.items():
        if not isinstance(item, dict):
            continue
        pos = tire_map.get(str(raw_pos).lower())
        if not pos:
            continue
        depth = _clean_text(item.get("tread_depth"))
        if depth:
            _set_field(granular, "tires", f"{pos}_tire_depth", status="normal", value=depth, source="tire_depths", evidence=depth, confidence=0.98)
        issue = _clean_text(item.get("issue"))
        if issue:
            status = "normal" if _is_clean_value(issue) else "issue"
            _set_field(granular, "tires", f"{pos}_tire_issue", status=status, value=issue, source="tire_depths", evidence=issue, confidence=0.96)


def _apply_damage_items(
    granular: dict[str, Any],
    damage_items: Any,
    repaired_panels: set[tuple[str, str]] | None = None,
) -> None:
    if not isinstance(damage_items, list):
        return
    if repaired_panels is None:
        repaired_panels = set()
    seen: set[tuple[str, str]] = set()  # (panel_lower, condition_lower) dedup
    for item in damage_items:
        if not isinstance(item, dict):
            continue
        # --- Repair filter ---
        if _is_repaired_damage(item, repaired_panels):
            continue
        # --- Deduplication (same panel + condition from different sources) ---
        panel_key = (
            _clean_text(item.get("panel"))
            or _clean_text(item.get("section_label"))
            or _clean_text(item.get("location"))
            or ""
        ).lower()
        cond_key = (
            _clean_text(item.get("condition"))
            or _clean_text(item.get("damage_type"))
            or ""
        ).lower()
        if panel_key and cond_key:
            dedup_key = (panel_key, cond_key)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
        text = _join_text(
            item.get("section_label"),
            item.get("section"),
            item.get("location"),
            item.get("panel"),
            item.get("condition"),
            item.get("damage_type"),
            item.get("description"),
            item.get("reported_severity"),
        )
        if not text:
            continue
        section_id, field_id = _map_text_to_field(text) or ("exterior", "further_disclosures")
        value = _damage_value(item, text)
        image_refs = _extract_image_refs(item)
        _set_field(
            granular,
            section_id,
            field_id,
            status="issue",
            value=value,
            source="damage_items",
            evidence=text,
            confidence=0.88 if field_id != "further_disclosures" else 0.72,
            image_refs=image_refs,
        )


def _apply_text_sources(
    granular: dict[str, Any],
    report: dict[str, Any],
    repaired_panels: set[tuple[str, str]] | None = None,
) -> None:
    text_items: list[tuple[str, str]] = []
    for key in ("problem_highlights", "remarks", "seller_comments_items", "announcements"):
        value = report.get(key)
        if isinstance(value, list):
            for item in value:
                text = _clean_text(item)
                if text:
                    text_items.append((key, text))
    seller_comments = _clean_text(report.get("seller_comments"))
    if seller_comments:
        text_items.append(("seller_comments", seller_comments))

    metadata = report.get("metadata")
    if isinstance(metadata, dict):
        report_page = metadata.get("report_page")
        if isinstance(report_page, dict):
            body_text = _clean_text(report_page.get("body_text"))
            if body_text:
                in_repaired = False
                for line in body_text.splitlines():
                    stripped = line.strip()
                    if re.match(r"^Repaired\s*$", stripped, re.I):
                        in_repaired = True
                        continue
                    if in_repaired and re.match(
                        r"^(IMAGE\s+DESCRIPTION|[A-Z ]{6,}.*\[)", stripped, re.I
                    ):
                        if not re.match(r"^IMAGE\s+DESCRIPTION", stripped, re.I):
                            in_repaired = False
                        continue
                    if in_repaired:
                        continue  # skip lines inside the Repaired section
                    cleaned = _clean_text(line)
                    if cleaned and _looks_like_damage_or_issue(cleaned):
                        text_items.append(("report_body_text", cleaned))

    for source, text in text_items:
        mapped = _map_text_to_field(text)
        if not mapped:
            continue
        section_id, field_id = mapped
        if _is_clean_value(text):
            continue
        _set_field(
            granular,
            section_id,
            field_id,
            status="issue",
            value=_issue_sentence(text),
            source=source,
            evidence=text,
            confidence=0.78,
        )


def _map_text_to_field(text: str) -> tuple[str, str] | None:
    # Interior trim terms should win over broad "rear passenger door" exterior matches.
    if re.search(r"\b(passenger|right|rh)\b.*\b(rear|back)\b.*\b(door panel|arm ?rest|trim)\b|\b(rear|back)\b.*\b(passenger|right|rh)\b.*\b(door panel|arm ?rest|trim)\b", text, re.I):
        return "interior", "passenger_rear_door_panel"
    if re.search(r"\b(driver|left|lh)\b.*\b(rear|back)\b.*\b(door panel|arm ?rest|trim)\b|\b(rear|back)\b.*\b(driver|left|lh)\b.*\b(door panel|arm ?rest|trim)\b", text, re.I):
        return "interior", "driver_rear_door_panel"
    for section_id, field_id, pattern in _FIELD_PATTERNS:
        if pattern.search(text):
            return section_id, field_id
    if re.search(r"\b(door panel|arm ?rest|seat|headliner|dash|interior|leather|vinyl|cloth)\b", text, re.I):
        return "interior", "driver_seat"
    if re.search(r"\b(scratch|dent|ding|chip|crack|scuff|damage|rust|paint|bumper|door|fender|quarter)\b", text, re.I):
        return "exterior", "further_disclosures"
    return None


def _set_field(
    granular: dict[str, Any],
    section_id: str,
    field_id: str,
    *,
    status: str,
    value: str,
    source: str,
    evidence: str | None,
    confidence: float,
    image_refs: list[str] | None = None,
) -> None:
    section = granular.get(section_id)
    if not isinstance(section, dict):
        return
    fields = section.get("fields")
    if not isinstance(fields, dict) or field_id not in fields:
        return
    current = dict(fields[field_id])
    existing_value = str(current.get("value") or "")
    current_status = str(current.get("status") or "normal")
    if current_status == "issue" and status != "issue":
        return
    if current_status == "issue" and existing_value and not existing_value.startswith("Normal -"):
        value = f"{existing_value}; {value}" if value not in existing_value else existing_value
    existing_source = str(current.get("source") or "default")
    current.update(
        {
            "status": status,
            "value": value,
            "source": source,
            "confidence": confidence if existing_source == "default" else max(float(current.get("confidence") or 0), confidence),
        }
    )
    if evidence:
        current["evidence"] = _merge_unique(current.get("evidence"), [evidence])
    if image_refs:
        current["image_refs"] = _merge_unique(current.get("image_refs"), image_refs)
    fields[field_id] = current


def _refresh_issue_counts(granular: dict[str, Any]) -> None:
    for section in granular.values():
        if not isinstance(section, dict):
            continue
        fields = section.get("fields")
        if not isinstance(fields, dict):
            section["issue_count"] = 0
            continue
        section["issue_count"] = sum(1 for field in fields.values() if isinstance(field, dict) and field.get("status") == "issue")


def _is_default_inspection_value(value: str, field: dict[str, Any]) -> bool:
    normalized = value.strip().lower()
    if field.get("is_default") is True and normalized in {"not inspected", "not specified", "not available"}:
        return True
    return normalized in {"not inspected", "not specified", "not available"}


def _is_clean_value(value: str) -> bool:
    return bool(_CLEAN_VALUE_RE.search(value.strip()))


def _looks_like_damage_or_issue(value: str) -> bool:
    return bool(re.search(r"\b(scratch|dent|ding|chip|crack|scuff|damage|rip|tear|torn|stain|odor|smoke|leak|warning|check engine|curb|rash)\b", value, re.I))


def _extract_repaired_panels(report: dict[str, Any]) -> set[tuple[str, str]]:
    """Parse the body_text 'Repaired' section and return (panel, condition) tuples."""
    metadata = report.get("metadata")
    if not isinstance(metadata, dict):
        return set()
    report_page = metadata.get("report_page")
    if not isinstance(report_page, dict):
        return set()
    body_text = report_page.get("body_text")
    if not isinstance(body_text, str):
        return set()

    repaired: set[tuple[str, str]] = set()
    in_repaired_section = False
    lines = body_text.splitlines()
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Detect "Repaired" section header (standalone line)
        if re.match(r"^Repaired\s*$", stripped, re.I):
            in_repaired_section = True
            continue
        # A new section header (all-caps with brackets or known headings) ends the repaired block
        if in_repaired_section and (
            re.match(r"^[A-Z ]{6,}.*\[", stripped)
            or re.match(r"^(IMAGE\s+DESCRIPTION|TIRES AND WHEELS|KEYS|OTHER|ADDITIONAL|MECHANICAL|INTERIOR|GRADING)\b", stripped, re.I)
        ):
            # "IMAGE  DESCRIPTION" is the column header row inside the Repaired
            # section — skip it but stay in the section.
            if re.match(r"^IMAGE\s+DESCRIPTION", stripped, re.I):
                continue
            in_repaired_section = False
            continue
        if in_repaired_section:
            # Lines inside the Repaired section look like:
            #   "LF Bumper Cover Scratch Heavy   1/2" to 1"      Completed"
            # Extract the panel name (first token group before a known condition keyword)
            m = re.match(
                r"^(?:0+\s+Picture.*|IMAGE\s+DESCRIPTION.*)$", stripped, re.I
            )
            if m:
                continue  # skip picture rows and header rows
            # Try to split into panel and condition using known condition keywords
            cond_match = re.search(
                r"\b(Scratch|Dent|Ding|Chip|Crack|Scuff|Curb Rash|Bug damage|"
                r"Rip|Tear|Torn|Stain|Missing|Broken|Bent|Faded|Peeling|"
                r"Prev Repair|Chipped|Heavy|Light|Paint Dmg|No Paint Dmg)\b",
                stripped,
                re.I,
            )
            if cond_match:
                panel = stripped[: cond_match.start()].strip()
                condition = cond_match.group(0).strip()
                if panel:
                    repaired.add((panel.lower(), condition.lower()))

    return repaired


def _is_repaired_damage(
    item: dict[str, Any],
    repaired_panels: set[tuple[str, str]],
) -> bool:
    """Return True when a damage item represents a completed repair."""
    # 1. Explicit repair_status field (forward-compatible with scraper contract)
    rs = _clean_text(item.get("repair_status"))
    if rs and rs.lower() in _REPAIR_STATUS_VALUES:
        return True

    # 2. section_label or section contains "Repaired"
    for key in ("section_label", "section"):
        val = _clean_text(item.get(key))
        if val and _REPAIRED_SECTION_RE.search(val):
            return True

    # 3. Cross-reference with body_text repaired panels
    if repaired_panels:
        panel = (
            _clean_text(item.get("panel"))
            or _clean_text(item.get("section_label"))
            or _clean_text(item.get("location"))
            or ""
        ).lower()
        condition = (
            _clean_text(item.get("condition"))
            or _clean_text(item.get("damage_type"))
            or ""
        ).lower()
        if panel and condition:
            for rep_panel, rep_cond in repaired_panels:
                if rep_panel == panel and rep_cond in condition:
                    return True

    return False


def _damage_value(item: dict[str, Any], fallback: str) -> str:
    condition = _clean_text(item.get("condition")) or _clean_text(item.get("damage_type"))
    severity = _clean_text(item.get("severity_label")) or _clean_text(item.get("reported_severity"))
    panel = _clean_text(item.get("panel")) or _clean_text(item.get("section_label")) or _clean_text(item.get("location"))
    parts = [part for part in (severity, condition, panel) if part]
    if parts:
        return "Damage reported: " + " - ".join(parts)
    return _issue_sentence(fallback)


def _issue_sentence(text: str) -> str:
    text = text.strip().rstrip(".")
    if re.match(r"^(damage|issue|reported)\b", text, re.I):
        return text
    return f"Issue reported: {text}"


def _extract_image_refs(item: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in ("pics", "photos", "pictures", "images", "image_urls", "photo_urls", "imageRefs", "image_refs"):
        bucket = item.get(key)
        if isinstance(bucket, str) and bucket:
            refs.append(bucket)
        elif isinstance(bucket, list):
            for entry in bucket:
                if isinstance(entry, str) and entry:
                    refs.append(entry)
                elif isinstance(entry, dict):
                    text = _clean_text(entry.get("url")) or _clean_text(entry.get("href")) or _clean_text(entry.get("id"))
                    if text:
                        refs.append(text)
    return _merge_unique([], refs)


def _join_text(*values: Any) -> str:
    return " ".join(text for text in (_clean_text(value) for value in values) if text)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _clean_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return _merge_unique([], [text for text in (_clean_text(item) for item in value) if text])


def _merge_unique(existing: Any, incoming: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    if isinstance(existing, list):
        iterable = [*existing, *incoming]
    else:
        iterable = incoming
    for item in iterable:
        text = _clean_text(item)
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        merged.append(text)
    return merged


def _coerce_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
