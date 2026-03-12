from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.constants import AuctionPlatform, InventorySourceType, OveDetailRequestStatus


def _normalize_vin(value: str) -> str:
    text = value.strip().upper()
    if len(text) != 17:
        raise ValueError("VIN must be 17 characters")
    return text


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
    condition_grade: str | None = None
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
