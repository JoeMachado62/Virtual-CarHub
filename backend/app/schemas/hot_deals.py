from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.constants import AuctionPlatform
from app.schemas.ove_inventory import OveImagePayload, OveListingSnapshot


class HotDealVehiclePayload(BaseModel):
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
    images: list[str] = Field(default_factory=list)
    features_raw: list[str] = Field(default_factory=list)
    features_normalized: dict[str, Any] = Field(default_factory=dict)


class HotDealPricingPayload(BaseModel):
    mmr_value: float
    asking_price: float
    deal_delta: float
    deal_delta_pct: float | None = None
    deal_label: str
    deal_rank: int = 100


class HotDealCrScreenPayload(BaseModel):
    status: str = "passed"
    version: str | None = None
    reasons: list[str] = Field(default_factory=list)
    positive_highlights: list[str] = Field(default_factory=list)
    excluded_signals_checked: list[str] = Field(default_factory=list)


class HotDealDetailPayload(BaseModel):
    images: list[OveImagePayload] = Field(default_factory=list)
    condition_report: dict[str, Any] = Field(default_factory=dict)
    seller_comments: str | None = None
    listing_snapshot: OveListingSnapshot = Field(default_factory=OveListingSnapshot)
    sync_metadata: dict[str, Any] = Field(default_factory=dict)


class HotDealMarketingPayload(BaseModel):
    title: str | None = None
    summary: str | None = None
    priority: int | None = None
    featured_until: datetime | None = None
    channels: list[str] = Field(default_factory=list)


class HotDealRawRefsPayload(BaseModel):
    listing_json_ref: str | None = None
    condition_report_html_ref: str | None = None
    scraper_run_log_ref: str | None = None


class HotDealItemPayload(BaseModel):
    vin: str
    listing_id: str | None = None
    listing_url: str | None = None
    source_platform: AuctionPlatform | None = None
    auction_start_at: datetime | None = None
    auction_end_at: datetime
    vehicle: HotDealVehiclePayload
    pricing: HotDealPricingPayload
    cr_screen: HotDealCrScreenPayload = Field(default_factory=HotDealCrScreenPayload)
    detail: HotDealDetailPayload
    marketing: HotDealMarketingPayload = Field(default_factory=HotDealMarketingPayload)
    raw_refs: HotDealRawRefsPayload = Field(default_factory=HotDealRawRefsPayload)

    @field_validator("vin")
    @classmethod
    def validate_vin(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if len(cleaned) != 17:
            raise ValueError("VIN must be 17 characters")
        return cleaned

    @model_validator(mode="after")
    def validate_hot_deal(self) -> "HotDealItemPayload":
        if self.cr_screen.status.lower() != "passed":
            raise ValueError("Hot Deal items must have cr_screen.status='passed'")
        if not self.detail.condition_report:
            raise ValueError("Hot Deal items require detail.condition_report")
        return self


class HotDealIngestRequest(BaseModel):
    source_list_name: str = "VHC Marketing List"
    source_platform: AuctionPlatform = AuctionPlatform.MANHEIM
    batch_id: str
    snapshot_mode: Literal["full_replace", "append"] = "full_replace"
    scraped_at: datetime | None = None
    filter_rules: dict[str, Any] = Field(default_factory=dict)
    deals: list[HotDealItemPayload] = Field(default_factory=list)

    @field_validator("batch_id")
    @classmethod
    def validate_batch_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("batch_id is required")
        return cleaned

