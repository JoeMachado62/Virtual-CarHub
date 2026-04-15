from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.constants import AuctionPlatform, InventorySourceType, OveDetailRequestStatus


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


def _condition_report_has_content(value: dict[str, Any]) -> bool:
    for item in value.values():
        if item not in (None, "", [], {}):
            return True
    return False


def _normalize_condition_report_payload(value: Any) -> dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValueError("condition_report must be an object")

    report = dict(value)

    overall_grade = _clean_text(report.get("overall_grade")) or _clean_text(report.get("grade"))
    if overall_grade:
        report["overall_grade"] = overall_grade

    had_direct_announcements = "announcements" in report
    metadata_raw = report.get("metadata")
    metadata = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}

    report_link_raw = metadata.get("report_link")
    report_link = dict(report_link_raw) if isinstance(report_link_raw, dict) else {}
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
