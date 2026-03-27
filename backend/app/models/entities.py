from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.constants import DealState, FundingState, ProfileTier, ReturnState
from app.core.constants import (
    AuctionPlatform,
    ImageContext,
    ImageJobStatus,
    ImageTier,
    InspectionStatus,
    OveDetailRequestStatus,
)
from app.db.base import Base, TimestampMixin


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    first_name: Mapped[str | None] = mapped_column(String(120))
    last_name: Mapped[str | None] = mapped_column(String(120))
    phone: Mapped[str | None] = mapped_column(String(30))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_preapproved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Manual admin override
    preapproved_amount: Mapped[float | None] = mapped_column(Float)  # Max approved loan amount
    preapproved_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # Expiration date

    profile: Mapped[BuyerProfile | None] = relationship(back_populates="user", uselist=False)
    deals: Mapped[list[Deal]] = relationship(back_populates="user")


class BuyerProfile(Base, TimestampMixin):
    __tablename__ = "buyer_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    profile_tier: Mapped[ProfileTier] = mapped_column(Enum(ProfileTier), default=ProfileTier.QUICK)
    bfv_json: Mapped[dict] = mapped_column(JSON, default=dict)
    intake_steps_complete: Mapped[list] = mapped_column(JSON, default=list)
    hard_constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    demographics: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False)

    user: Mapped[User] = relationship(back_populates="profile")


class Deal(Base, TimestampMixin):
    __tablename__ = "deals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    stage: Mapped[DealState] = mapped_column(Enum(DealState), default=DealState.LEAD, nullable=False)
    funding_state: Mapped[FundingState] = mapped_column(
        Enum(FundingState), default=FundingState.CREDIT_APP_PENDING, nullable=False
    )
    assigned_agent: Mapped[str | None] = mapped_column(String(80))
    deal_desk_flags: Mapped[list] = mapped_column(JSON, default=list)
    human_checkpoint_required: Mapped[bool] = mapped_column(Boolean, default=False)
    selected_vin: Mapped[str | None] = mapped_column(String(17), index=True)
    ghl_contact_id: Mapped[str | None] = mapped_column(String(80), index=True)
    ghl_opportunity_id: Mapped[str | None] = mapped_column(String(80), index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Document tracking fields
    documents_collected: Mapped[dict] = mapped_column(JSON, default=dict)  # Track document types and GHL URLs
    preapproval_letter_url: Mapped[str | None] = mapped_column(String(500))  # Direct link to pre-approval letter
    loan_documents_url: Mapped[str | None] = mapped_column(String(500))  # Direct link to loan docs
    identity_verified: Mapped[bool] = mapped_column(Boolean, default=False)  # ID verification status
    income_verified: Mapped[bool] = mapped_column(Boolean, default=False)  # Income verification status
    external_financing_bank: Mapped[str | None] = mapped_column(String(120))  # Bank name for external financing
    external_financing_status: Mapped[str | None] = mapped_column(String(50))  # Status of external loan

    user: Mapped[User] = relationship(back_populates="deals")
    matches: Mapped[list[VehicleMatch]] = relationship(back_populates="deal")


class Vehicle(Base, TimestampMixin):
    __tablename__ = "vehicles"

    vin: Mapped[str] = mapped_column(String(17), primary_key=True)
    listing_id: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    make: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    trim: Mapped[str | None] = mapped_column(String(120))
    body_type: Mapped[str | None] = mapped_column(String(40), index=True)
    sub_body_type: Mapped[str | None] = mapped_column(String(80))
    engine_type: Mapped[str | None] = mapped_column(String(40), index=True)
    cylinders: Mapped[int | None] = mapped_column(Integer)
    forced_induction: Mapped[str | None] = mapped_column(String(40))
    drivetrain: Mapped[str | None] = mapped_column(String(20))
    mpg_combined: Mapped[float | None] = mapped_column(Float)
    ev_range: Mapped[int | None] = mapped_column(Integer)
    towing_capacity_lbs: Mapped[int | None] = mapped_column(Integer)
    odometer: Mapped[int | None] = mapped_column(Integer)
    condition_grade: Mapped[str | None] = mapped_column(String(20), index=True)
    price_asking: Mapped[float] = mapped_column(Float, nullable=False, index=True)
    price_wholesale_est: Mapped[float | None] = mapped_column(Float)
    location_zip: Mapped[str | None] = mapped_column(String(10), index=True)
    location_state: Mapped[str | None] = mapped_column(String(2), index=True)
    source_type: Mapped[str | None] = mapped_column(String(30), index=True)
    source_url: Mapped[str | None] = mapped_column(String(500))
    images: Mapped[list] = mapped_column(JSON, default=list)
    features_raw: Mapped[list] = mapped_column(JSON, default=list)
    features_normalized: Mapped[dict] = mapped_column(JSON, default=dict)
    bfv_compatibility_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    last_seen_active: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    available: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    quality_firewall_pass: Mapped[bool | None] = mapped_column(Boolean)


class VehicleTaxonomyCache(Base, TimestampMixin):
    __tablename__ = "vehicle_taxonomy_cache"
    __table_args__ = (
        UniqueConstraint("year", "make", "model", "trim", name="uq_vehicle_taxonomy_cache_ymmt"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source: Mapped[str] = mapped_column(String(40), default="marketcheck", nullable=False, index=True)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    make: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    trim: Mapped[str] = mapped_column(String(120), default="", nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class VehicleImageAsset(Base, TimestampMixin):
    __tablename__ = "vehicle_image_assets"
    __table_args__ = (UniqueConstraint("vin", "tier", "external_url", name="uq_vehicle_image_assets_vin_tier_url"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    vin: Mapped[str] = mapped_column(ForeignKey("vehicles.vin", ondelete="CASCADE"), index=True)
    tier: Mapped[ImageTier] = mapped_column(Enum(ImageTier), nullable=False, index=True)
    context: Mapped[ImageContext] = mapped_column(Enum(ImageContext), default=ImageContext.MARKETING, index=True)
    role: Mapped[str] = mapped_column(String(40), default="gallery", index=True)
    source_kind: Mapped[str] = mapped_column(String(40), default="marketcheck", index=True)
    source_platform: Mapped[AuctionPlatform | None] = mapped_column(Enum(AuctionPlatform), nullable=True, index=True)
    source_listing_id: Mapped[str | None] = mapped_column(String(120))
    source_image_id: Mapped[str | None] = mapped_column(String(120))
    external_url: Mapped[str | None] = mapped_column(String(1200))
    storage_key: Mapped[str | None] = mapped_column(String(600))
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_original: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processing_status: Mapped[ImageJobStatus] = mapped_column(
        Enum(ImageJobStatus), default=ImageJobStatus.COMPLETED, nullable=False, index=True
    )
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class VehicleImageJob(Base, TimestampMixin):
    __tablename__ = "vehicle_image_jobs"
    __table_args__ = (
        UniqueConstraint(
            "vin",
            "tier",
            "source_fingerprint",
            name="uq_vehicle_image_jobs_vin_tier_fingerprint",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    vin: Mapped[str] = mapped_column(ForeignKey("vehicles.vin", ondelete="CASCADE"), index=True)
    tier: Mapped[ImageTier] = mapped_column(Enum(ImageTier), nullable=False, index=True)
    trigger_event: Mapped[str] = mapped_column(String(80), default="unknown")
    status: Mapped[ImageJobStatus] = mapped_column(Enum(ImageJobStatus), default=ImageJobStatus.PENDING, index=True)
    source_fingerprint: Mapped[str] = mapped_column(String(255), default="")
    manifest_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class VehicleInspectionReport(Base, TimestampMixin):
    __tablename__ = "vehicle_inspection_reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    vin: Mapped[str] = mapped_column(ForeignKey("vehicles.vin", ondelete="CASCADE"), index=True)
    deal_id: Mapped[str | None] = mapped_column(ForeignKey("deals.id", ondelete="SET NULL"), index=True)
    platform: Mapped[AuctionPlatform] = mapped_column(Enum(AuctionPlatform), nullable=False, index=True)
    inspection_status: Mapped[InspectionStatus] = mapped_column(
        Enum(InspectionStatus), default=InspectionStatus.PENDING, nullable=False, index=True
    )
    lot_number: Mapped[str | None] = mapped_column(String(120), index=True)
    auction_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    inspector_id: Mapped[str | None] = mapped_column(String(80))
    platform_native_grade: Mapped[str | None] = mapped_column(String(40))
    platform_grade_scale: Mapped[str | None] = mapped_column(String(40))
    vch_normalized_grade: Mapped[str | None] = mapped_column(String(20))
    buyer_protection_json: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_report_json: Mapped[dict] = mapped_column(JSON, default=dict)
    normalized_report_json: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    normalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    images: Mapped[list["VehicleInspectionImage"]] = relationship(back_populates="report")


class VehicleInspectionImage(Base, TimestampMixin):
    __tablename__ = "vehicle_inspection_images"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    inspection_report_id: Mapped[str] = mapped_column(
        ForeignKey("vehicle_inspection_reports.id", ondelete="CASCADE"), index=True
    )
    vin: Mapped[str] = mapped_column(ForeignKey("vehicles.vin", ondelete="CASCADE"), index=True)
    image_type: Mapped[str] = mapped_column(String(30), default="inspection", index=True)
    filename: Mapped[str] = mapped_column(String(255))
    source_url: Mapped[str | None] = mapped_column(String(1200))
    storage_key: Mapped[str | None] = mapped_column(String(600))
    sha256: Mapped[str | None] = mapped_column(String(64), index=True)
    linked_finding_path: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)

    report: Mapped[VehicleInspectionReport] = relationship(back_populates="images")


class OveVehicleDetail(Base, TimestampMixin):
    __tablename__ = "ove_vehicle_details"

    vin: Mapped[str] = mapped_column(
        ForeignKey("vehicles.vin", ondelete="CASCADE"),
        primary_key=True,
    )
    source_platform: Mapped[AuctionPlatform] = mapped_column(
        Enum(AuctionPlatform),
        default=AuctionPlatform.MANHEIM,
        nullable=False,
        index=True,
    )
    seller_comments: Mapped[str | None] = mapped_column(Text)
    images_json: Mapped[list] = mapped_column(JSON, default=list)
    condition_report_json: Mapped[dict] = mapped_column(JSON, default=dict)
    listing_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    sync_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    page_url: Mapped[str | None] = mapped_column(String(1200))
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class OveDetailRequest(Base, TimestampMixin):
    __tablename__ = "ove_detail_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    vin: Mapped[str] = mapped_column(String(17), index=True, nullable=False)
    source_platform: Mapped[AuctionPlatform] = mapped_column(
        Enum(AuctionPlatform),
        default=AuctionPlatform.MANHEIM,
        nullable=False,
        index=True,
    )
    status: Mapped[OveDetailRequestStatus] = mapped_column(
        Enum(OveDetailRequestStatus),
        default=OveDetailRequestStatus.PENDING,
        nullable=False,
        index=True,
    )
    requested_by: Mapped[str] = mapped_column(String(80), default="system")
    request_source: Mapped[str] = mapped_column(String(80), default="api")
    reason: Mapped[str | None] = mapped_column(String(255))
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    detail_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class VehicleMatch(Base, TimestampMixin):
    __tablename__ = "vehicle_matches"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    vin: Mapped[str] = mapped_column(ForeignKey("vehicles.vin", ondelete="CASCADE"), index=True)
    match_score: Mapped[float] = mapped_column(Float, nullable=False)
    explainability_text: Mapped[str] = mapped_column(Text, default="")
    estimated_transport_cost: Mapped[float] = mapped_column(Float, default=0.0)
    estimated_registration: Mapped[float] = mapped_column(Float, default=0.0)
    vch_fee: Mapped[float] = mapped_column(Float, default=0.0)
    marketcheck_retail: Mapped[float | None] = mapped_column(Float)
    estimated_otd: Mapped[float] = mapped_column(Float, default=0.0)
    danny_savings: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(30), default="recommended", index=True)

    deal: Mapped[Deal] = relationship(back_populates="matches")
    vehicle: Mapped[Vehicle] = relationship()


class GarageItem(Base, TimestampMixin):
    __tablename__ = "garage_items"
    __table_args__ = (UniqueConstraint("deal_id", "vin", name="uq_garage_items_deal_vin"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    vin: Mapped[str] = mapped_column(ForeignKey("vehicles.vin", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="saved", nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(40), default="inventory")
    acquisition_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    vehicle: Mapped[Vehicle] = relationship()


class FundingCase(Base, TimestampMixin):
    __tablename__ = "funding_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), unique=True, index=True)
    funding_state: Mapped[FundingState] = mapped_column(Enum(FundingState), nullable=False)
    lender_id: Mapped[str | None] = mapped_column(String(120))
    approval_amount: Mapped[float | None] = mapped_column(Float)
    apr: Mapped[float | None] = mapped_column(Float)
    term_months: Mapped[int | None] = mapped_column(Integer)
    conditions: Mapped[list] = mapped_column(JSON, default=list)


class Document(Base, TimestampMixin):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    doc_type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    signer_role: Mapped[str] = mapped_column(String(40), default="buyer")
    signed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    storage_url: Mapped[str | None] = mapped_column(String(500))


class AcquisitionOrder(Base, TimestampMixin):
    __tablename__ = "acquisition_orders"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    vin: Mapped[str | None] = mapped_column(String(17), index=True)
    acquisition_path: Mapped[str | None] = mapped_column(String(40))
    bid_ceiling: Mapped[float | None] = mapped_column(Float)
    actual_price: Mapped[float | None] = mapped_column(Float)
    seller_id: Mapped[str | None] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(40), default="pending")


class TitleCase(Base, TimestampMixin):
    __tablename__ = "title_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), index=True)
    vin: Mapped[str] = mapped_column(String(17), index=True)
    title_state: Mapped[str | None] = mapped_column(String(2))
    title_type: Mapped[str | None] = mapped_column(String(40))
    lien_status: Mapped[str | None] = mapped_column(String(40))
    exceptions: Mapped[list] = mapped_column(JSON, default=list)


class Carrier(Base):
    __tablename__ = "carriers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    mc_number: Mapped[str | None] = mapped_column(String(60), unique=True)
    on_time_rate: Mapped[float] = mapped_column(Float, default=1.0)
    damage_claim_rate: Mapped[float] = mapped_column(Float, default=0.0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Shipment(Base, TimestampMixin):
    __tablename__ = "shipments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), unique=True, index=True)
    vin: Mapped[str] = mapped_column(String(17), index=True)
    carrier_id: Mapped[str | None] = mapped_column(ForeignKey("carriers.id"))
    tracking_url: Mapped[str | None] = mapped_column(String(500))
    status: Mapped[str] = mapped_column(String(40), default="pending")
    delivery_condition_report: Mapped[dict] = mapped_column(JSON, default=dict)
    eta: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class DealerPartner(Base, TimestampMixin):
    __tablename__ = "dealer_partners"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(30))
    dealer_license: Mapped[str | None] = mapped_column(String(100))
    rooftop_locations: Mapped[list] = mapped_column(JSON, default=list)
    preferred_brands: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ReturnCase(Base, TimestampMixin):
    __tablename__ = "return_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), unique=True, index=True)
    vin: Mapped[str] = mapped_column(String(17), index=True)
    return_reason: Mapped[str] = mapped_column(Text, nullable=False)
    return_state: Mapped[ReturnState] = mapped_column(
        Enum(ReturnState), default=ReturnState.RETURN_PENDING, nullable=False
    )
    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    vehicle_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refund_amount: Mapped[float] = mapped_column(Float, default=0.0)
    restocking_fee: Mapped[float] = mapped_column(Float, default=0.0)
    damage_deduction: Mapped[float] = mapped_column(Float, default=0.0)
    buyer_transport_responsibility: Mapped[bool] = mapped_column(Boolean, default=True)


class DealOutcome(Base):
    __tablename__ = "deal_outcomes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="CASCADE"), unique=True, index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    lead_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cycle_time_days: Mapped[int | None] = mapped_column(Integer)
    time_in_each_state: Mapped[dict] = mapped_column(JSON, default=dict)
    acquisition_cost: Mapped[float | None] = mapped_column(Float)
    auction_fees: Mapped[float | None] = mapped_column(Float)
    transport_cost: Mapped[float | None] = mapped_column(Float)
    recon_cost: Mapped[float | None] = mapped_column(Float)
    vch_fee: Mapped[float | None] = mapped_column(Float)
    sell_price: Mapped[float | None] = mapped_column(Float)
    gross_margin: Mapped[float | None] = mapped_column(Float)
    gross_margin_pct: Mapped[float | None] = mapped_column(Float)
    market_retail_at_close: Mapped[float | None] = mapped_column(Float)
    spread_vs_retail: Mapped[float | None] = mapped_column(Float)
    vin: Mapped[str | None] = mapped_column(String(17))
    year: Mapped[int | None] = mapped_column(Integer)
    make: Mapped[str | None] = mapped_column(String(80))
    model: Mapped[str | None] = mapped_column(String(80))
    body_type: Mapped[str | None] = mapped_column(String(40))
    odometer: Mapped[int | None] = mapped_column(Integer)
    condition_grade: Mapped[str | None] = mapped_column(String(20))
    source_type: Mapped[str | None] = mapped_column(String(30))
    match_score: Mapped[float | None] = mapped_column(Float)
    buyer_profile_tier: Mapped[str | None] = mapped_column(String(20))
    lead_source: Mapped[str | None] = mapped_column(String(120))
    utm_campaign: Mapped[str | None] = mapped_column(String(120))
    utm_medium: Mapped[str | None] = mapped_column(String(120))
    referral_code: Mapped[str | None] = mapped_column(String(60))
    loss_reason: Mapped[str | None] = mapped_column(String(250))
    loss_stage: Mapped[str | None] = mapped_column(String(60))
    return_reason: Mapped[str | None] = mapped_column(String(250))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    deal_id: Mapped[str | None] = mapped_column(ForeignKey("deals.id", ondelete="SET NULL"), index=True)
    event_type: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(50), nullable=False)
    previous_state: Mapped[str | None] = mapped_column(String(40))
    new_state: Mapped[str | None] = mapped_column(String(40))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    deal_id: Mapped[str | None] = mapped_column(ForeignKey("deals.id", ondelete="SET NULL"), index=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    channel: Mapped[str] = mapped_column(String(20), default="in_app")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class FeatureFlag(Base):
    __tablename__ = "feature_flags"

    name: Mapped[str] = mapped_column(String(80), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class ConfigEntry(Base):
    __tablename__ = "config"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSON, default=dict)
    description: Mapped[str | None] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    deal_id: Mapped[str | None] = mapped_column(ForeignKey("deals.id", ondelete="SET NULL"), index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    context_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class EvoxVifCache(Base, TimestampMixin):
    """Cache of the EVOX VIF (Vehicle Image Factory) list mapping vehicle
    configurations to VIFIDs and available product types."""

    __tablename__ = "evox_vif_cache"
    __table_args__ = (
        UniqueConstraint("vifnum", name="uq_evox_vif_cache_vifnum"),
        Index("ix_evox_vif_cache_ymmt", "year", "make", "model", "trim"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    vifnum: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    orgnum: Mapped[int | None] = mapped_column(Integer)
    sendnum: Mapped[int | None] = mapped_column(Integer)
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    make: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    trim: Mapped[str] = mapped_column(String(120), default="", nullable=False, index=True)
    doors: Mapped[int | None] = mapped_column(Integer)
    body: Mapped[str | None] = mapped_column(String(40), index=True)
    cab: Mapped[str | None] = mapped_column(String(40))
    wheels: Mapped[str | None] = mapped_column(String(20))
    vin_photographed: Mapped[str | None] = mapped_column(String(17))
    date_delivered: Mapped[str | None] = mapped_column(String(20))
    has_btl: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_colors: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_stills: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_exterior: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_interior: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_hdspin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_ext_color: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class EvoxColorCache(Base, TimestampMixin):
    """Cache of available EVOX colors per VIFID, used to match vehicle paint
    codes to EVOX color codes for color-accurate image requests."""

    __tablename__ = "evox_color_cache"
    __table_args__ = (
        UniqueConstraint("vifnum", "color_code", name="uq_evox_color_cache_vif_code"),
        Index("ix_evox_color_cache_vif_simple", "vifnum", "color_simpletitle"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    vifnum: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    color_code: Mapped[str] = mapped_column(String(40), nullable=False)
    color_title: Mapped[str] = mapped_column(String(120), nullable=False)
    color_simpletitle: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
