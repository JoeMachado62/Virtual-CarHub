from datetime import UTC, datetime
from types import SimpleNamespace

from sqlalchemy import delete, select

from app.core.config import settings
from app.core.constants import (
    AuctionPlatform,
    DealState,
    ImageContext,
    ImageDisplayMode,
    ImageTier,
    InspectionStatus,
)
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.entities import (
    OveVehicleDetail,
    Vehicle,
    VehicleImageAsset,
    VehicleImageJob,
    VehicleInspectionImage,
    VehicleInspectionReport,
)
from app.services.image_pipeline_service import (
    _asset_url,
    ensure_tier2_hero_job,
    ensure_tier3_processing_job,
    resolve_vehicle_display_context,
    sync_marketcheck_source_assets,
)
from app.services.chromedata_service import CHROMEDATA_SOURCE_KIND


def test_asset_url_prefers_storage_key_over_external_url(monkeypatch) -> None:
    monkeypatch.setattr(settings, "object_storage_public_base_url", "https://assets.example.com")
    monkeypatch.setattr(settings, "aws_cloudfront_domain", "")
    monkeypatch.setattr(settings, "s3_assets_bucket", "")
    asset = SimpleNamespace(
        storage_key="source-cache/VIN123/marketcheck/001.jpg",
        external_url="https://source.example/VIN123/001.jpg",
    )

    assert _asset_url(asset) == "https://assets.example.com/source-cache/VIN123/marketcheck/001.jpg"


def _make_vehicle(vin: str) -> Vehicle:
    return Vehicle(
        vin=vin,
        listing_id=f"{vin}-listing",
        year=2024,
        make="Test",
        model="Vehicle",
        price_asking=29995,
        source_type="marketcheck",
        images=[f"https://source.example/{vin}/fallback-1.jpg", f"https://source.example/{vin}/fallback-2.jpg"],
        available=True,
    )


def test_marketing_context_prefers_tier3_gallery_and_tier2_hero(monkeypatch) -> None:
    init_db()
    vin = "1HGBH41JXMN109186"
    with SessionLocal() as db:
        monkeypatch.setattr(settings, "imagin_enabled", False)
        db.execute(delete(VehicleInspectionImage).where(VehicleInspectionImage.vin == vin))
        db.execute(delete(VehicleInspectionReport).where(VehicleInspectionReport.vin == vin))
        db.execute(delete(VehicleImageJob).where(VehicleImageJob.vin == vin))
        db.execute(delete(VehicleImageAsset).where(VehicleImageAsset.vin == vin))
        db.execute(delete(Vehicle).where(Vehicle.vin == vin))
        db.commit()

        vehicle = _make_vehicle(vin)
        db.add(vehicle)
        db.flush()

        sync_marketcheck_source_assets(
            db,
            vin=vin,
            listing_id=vehicle.listing_id,
            image_urls=[f"https://source.example/{vin}/source-1.jpg", f"https://source.example/{vin}/source-2.jpg"],
        )
        db.add(
            VehicleImageAsset(
                vin=vin,
                tier=ImageTier.TIER2_HERO,
                context=ImageContext.MARKETING,
                role="hero",
                source_kind="generated",
                external_url=f"https://cdn.example/{vin}/hero.webp",
                is_primary=True,
            )
        )
        db.add(
            VehicleImageAsset(
                vin=vin,
                tier=ImageTier.TIER3_PROCESSED,
                context=ImageContext.MARKETING,
                role="gallery",
                source_kind="generated",
                external_url=f"https://cdn.example/{vin}/processed-1.webp",
                display_order=1,
            )
        )
        db.add(
            VehicleImageAsset(
                vin=vin,
                tier=ImageTier.TIER3_PROCESSED,
                context=ImageContext.MARKETING,
                role="gallery",
                source_kind="generated",
                external_url=f"https://cdn.example/{vin}/processed-2.webp",
                display_order=2,
            )
        )
        db.commit()

        context = resolve_vehicle_display_context(db, vehicle=vehicle)

    assert context["mode"] == ImageDisplayMode.MARKETING.value
    assert context["hero_image"] == f"https://cdn.example/{vin}/hero.webp"
    assert context["gallery_images"] == [
        f"https://cdn.example/{vin}/processed-1.webp",
        f"https://cdn.example/{vin}/processed-2.webp",
    ]
    assert context["has_tier3_processed"] is True


def test_inspection_context_uses_verified_images_and_report() -> None:
    init_db()
    vin = "5YJ3E1EA7KF317000"
    with SessionLocal() as db:
        db.execute(delete(VehicleInspectionImage).where(VehicleInspectionImage.vin == vin))
        db.execute(delete(VehicleInspectionReport).where(VehicleInspectionReport.vin == vin))
        db.execute(delete(VehicleImageJob).where(VehicleImageJob.vin == vin))
        db.execute(delete(VehicleImageAsset).where(VehicleImageAsset.vin == vin))
        db.execute(delete(Vehicle).where(Vehicle.vin == vin))
        db.commit()

        vehicle = _make_vehicle(vin)
        db.add(vehicle)
        db.flush()

        report = VehicleInspectionReport(
            vin=vin,
            platform=AuctionPlatform.MANHEIM,
            inspection_status=InspectionStatus.NORMALIZED,
            lot_number="LOT-001",
            auction_date=datetime.now(UTC),
            normalized_report_json={"overall_grade": {"vch_normalized_grade": "B+"}},
            buyer_protection_json={"program": "DealShield"},
            is_current=True,
        )
        db.add(report)
        db.flush()

        db.add(
            VehicleInspectionImage(
                inspection_report_id=report.id,
                vin=vin,
                image_type="inspection",
                filename="inspection_001.jpg",
                source_url=f"https://inspect.example/{vin}/inspection_001.jpg",
                display_order=1,
            )
        )
        db.add(
            VehicleInspectionImage(
                inspection_report_id=report.id,
                vin=vin,
                image_type="disclosure",
                filename="disclosure_001.jpg",
                source_url=f"https://inspect.example/{vin}/disclosure_001.jpg",
                linked_finding_path="exterior.panels[0]",
                display_order=2,
            )
        )
        db.commit()

        context = resolve_vehicle_display_context(
            db,
            vehicle=vehicle,
            deal_stage=DealState.ACQUIRED,
            allow_protected_photos=True,
        )

    assert context["mode"] == ImageDisplayMode.INSPECTION_REPORT.value
    assert context["inspection_status"] == InspectionStatus.NORMALIZED.value
    assert context["gallery_images"] == [f"https://inspect.example/{vin}/inspection_001.jpg"]
    assert context["disclosure_images"] == [f"https://inspect.example/{vin}/disclosure_001.jpg"]
    assert context["condition_report"]["overall_grade"]["vch_normalized_grade"] == "B+"


def test_inspection_pending_when_stage_requires_inspection_but_no_report() -> None:
    init_db()
    vin = "1C4RJFBGXMC123456"
    with SessionLocal() as db:
        db.execute(delete(VehicleInspectionImage).where(VehicleInspectionImage.vin == vin))
        db.execute(delete(VehicleInspectionReport).where(VehicleInspectionReport.vin == vin))
        db.execute(delete(VehicleImageJob).where(VehicleImageJob.vin == vin))
        db.execute(delete(VehicleImageAsset).where(VehicleImageAsset.vin == vin))
        db.execute(delete(Vehicle).where(Vehicle.vin == vin))
        db.commit()

        vehicle = _make_vehicle(vin)
        db.add(vehicle)
        db.commit()

        context = resolve_vehicle_display_context(db, vehicle=vehicle, deal_stage=DealState.ACQUISITION_PENDING)

    assert context["mode"] == ImageDisplayMode.INSPECTION_PENDING.value
    assert context["inspection_status"] == InspectionStatus.PENDING.value
    # Dealer photos are gated for marketcheck source — gallery is empty until
    # reference images (ChromeData) are fetched or vehicle is added to garage.
    assert context["dealer_photos_gated"] is True
    assert context["gallery_images"] == []


def test_image_jobs_are_deduped_by_fingerprint() -> None:
    init_db()
    vin = "2C3CDXHG2PH512345"
    with SessionLocal() as db:
        db.execute(delete(VehicleImageJob).where(VehicleImageJob.vin == vin))
        db.execute(delete(Vehicle).where(Vehicle.vin == vin))
        db.commit()

        vehicle = _make_vehicle(vin)
        db.add(vehicle)
        db.commit()

        job_1 = ensure_tier2_hero_job(
            db,
            vin=vin,
            trigger_event="test_ingest",
            primary_image_url=f"https://source.example/{vin}/source-1.jpg",
        )
        job_2 = ensure_tier2_hero_job(
            db,
            vin=vin,
            trigger_event="test_ingest",
            primary_image_url=f"https://source.example/{vin}/source-1.jpg",
        )
        tier3_1 = ensure_tier3_processing_job(
            db,
            vin=vin,
            trigger_event="test_engagement",
            source_image_urls=[
                f"https://source.example/{vin}/source-1.jpg",
                f"https://source.example/{vin}/source-2.jpg",
            ],
        )
        tier3_2 = ensure_tier3_processing_job(
            db,
            vin=vin,
            trigger_event="test_engagement",
            source_image_urls=[
                f"https://source.example/{vin}/source-1.jpg",
                f"https://source.example/{vin}/source-2.jpg",
            ],
        )
        db.commit()

        jobs = db.scalars(select(VehicleImageJob).where(VehicleImageJob.vin == vin)).all()

    assert job_1 is not None
    assert tier3_1 is not None
    assert job_2 is not None
    assert tier3_2 is not None
    assert job_1.id == job_2.id
    assert tier3_1.id == tier3_2.id
    assert len(jobs) == 2


def test_auction_context_uses_chromedata_as_primary_and_appends_inspection_images(monkeypatch) -> None:
    init_db()
    vin = "1FTFW1E80MFA12345"
    with SessionLocal() as db:
        db.execute(delete(VehicleInspectionImage).where(VehicleInspectionImage.vin == vin))
        db.execute(delete(VehicleInspectionReport).where(VehicleInspectionReport.vin == vin))
        db.execute(delete(VehicleImageJob).where(VehicleImageJob.vin == vin))
        db.execute(delete(VehicleImageAsset).where(VehicleImageAsset.vin == vin))
        db.execute(delete(Vehicle).where(Vehicle.vin == vin))
        db.commit()

        monkeypatch.setattr(settings, "chromedata_enabled", True)
        monkeypatch.setattr(settings, "chromedata_media_username", "user")
        monkeypatch.setattr(settings, "chromedata_media_password", "pass")

        vehicle = Vehicle(
            vin=vin,
            listing_id=f"{vin}-listing",
            year=2024,
            make="Ford",
            model="F-150",
            trim="XLT",
            body_type="Truck",
            source_type="ove",
            price_asking=41250,
            images=[],
            features_normalized={
                "exterior_color": "Blue",
                "interior_color": "Black",
                "fuel_type": "Gasoline",
            },
            available=True,
        )
        db.add(vehicle)
        db.flush()

        db.add(
            VehicleImageAsset(
                vin=vin,
                tier=ImageTier.SOURCE_CACHE,
                context=ImageContext.MARKETING,
                role="hero",
                source_kind=CHROMEDATA_SOURCE_KIND,
                source_platform=AuctionPlatform.MANHEIM,
                source_listing_id=vehicle.listing_id,
                external_url=f"https://media.example/{vin}/01.jpg",
                display_order=0,
                is_primary=True,
                metadata_json={"provider": CHROMEDATA_SOURCE_KIND, "color_match_exact": True},
                active=True,
            )
        )
        db.add(
            VehicleImageAsset(
                vin=vin,
                tier=ImageTier.SOURCE_CACHE,
                context=ImageContext.MARKETING,
                role="gallery",
                source_kind=CHROMEDATA_SOURCE_KIND,
                source_platform=AuctionPlatform.MANHEIM,
                source_listing_id=vehicle.listing_id,
                external_url=f"https://media.example/{vin}/02.jpg",
                display_order=1,
                is_primary=False,
                metadata_json={"provider": CHROMEDATA_SOURCE_KIND, "color_match_exact": True},
                active=True,
            )
        )

        report = VehicleInspectionReport(
            vin=vin,
            platform=AuctionPlatform.MANHEIM,
            inspection_status=InspectionStatus.NORMALIZED,
            normalized_report_json={"overall_grade": {"vch_normalized_grade": "A-"}},
            is_current=True,
        )
        db.add(report)
        db.flush()
        db.add(
            VehicleInspectionImage(
                inspection_report_id=report.id,
                vin=vin,
                image_type="inspection",
                filename="inspection_001.jpg",
                source_url=f"https://inspect.example/{vin}/inspection_001.jpg",
                display_order=1,
            )
        )
        db.commit()

        context = resolve_vehicle_display_context(
            db,
            vehicle=vehicle,
            deal_stage=DealState.ACQUIRED,
            allow_protected_photos=True,
        )

    assert context["mode"] == ImageDisplayMode.INSPECTION_REPORT.value
    assert context["has_chromedata_stock"] is True
    assert context["hero_image"] == f"https://media.example/{vin}/01.jpg"
    assert context["inspection_images"] == [f"https://inspect.example/{vin}/inspection_001.jpg"]
    assert context["gallery_images"][0] == f"https://media.example/{vin}/01.jpg"
    assert context["gallery_images"][-1] == f"https://inspect.example/{vin}/inspection_001.jpg"
    assert "ChromeData factory reference images" in context["disclaimer"]


def test_auction_context_exposes_ove_role_images_without_internal_inspection_report(monkeypatch) -> None:
    init_db()
    vin = "1N4BL4EV2NN423240"
    with SessionLocal() as db:
        db.execute(delete(VehicleInspectionImage).where(VehicleInspectionImage.vin == vin))
        db.execute(delete(VehicleInspectionReport).where(VehicleInspectionReport.vin == vin))
        db.execute(delete(VehicleImageJob).where(VehicleImageJob.vin == vin))
        db.execute(delete(VehicleImageAsset).where(VehicleImageAsset.vin == vin))
        db.execute(delete(OveVehicleDetail).where(OveVehicleDetail.vin == vin))
        db.execute(delete(Vehicle).where(Vehicle.vin == vin))
        db.commit()

        monkeypatch.setattr(settings, "imagin_enabled", False)

        vehicle = Vehicle(
            vin=vin,
            listing_id=f"{vin}-listing",
            year=2022,
            make="Nissan",
            model="Altima",
            trim="2.5 SV",
            body_type="Sedan",
            source_type="ove",
            price_asking=18450,
            images=["https://images.example.com/hero.jpg"],
            available=True,
        )
        db.add(vehicle)
        db.flush()

        db.add(
            OveVehicleDetail(
                vin=vin,
                source_platform=AuctionPlatform.MANHEIM,
                images_json=[
                    {"url": "https://images.example.com/hero.jpg", "role": "hero", "display_order": 0, "is_primary": True},
                    {"url": "https://images.example.com/gallery-2.jpg", "role": "gallery", "display_order": 1, "is_primary": False},
                    {"url": "https://images.example.com/inspection-1.jpg", "role": "inspection", "display_order": 2, "is_primary": False},
                    {"url": "https://images.example.com/disclosure-1.jpg", "role": "disclosure", "display_order": 3, "is_primary": False},
                ],
                condition_report_json={
                    "overall_grade": "4.6",
                    "metadata": {
                        "report_link": {"href": "http://content.liquidmotors.com/IR/15614/38020971.html"},
                        "announcementsEnrichment": {"announcements": ["Open Recall"]},
                    },
                    "announcements": ["Open Recall"],
                    "vehicle_history": {"owners": 1, "accidents": 0},
                    "damage_items": [],
                    "damage_summary": {"total_items": 0},
                    "tire_depths": {
                        "lf": {"position_label": "LF", "tread_depth": "6/32"},
                        "rf": {"position_label": "RF", "tread_depth": "6/32"},
                        "lr": {"position_label": "LR", "tread_depth": "7/32"},
                        "rr": {"position_label": "RR", "tread_depth": "7/32"},
                    },
                },
            )
        )
        db.commit()

        context = resolve_vehicle_display_context(db, vehicle=vehicle, allow_protected_photos=True)

    assert context["inspection_status"] == InspectionStatus.VERIFIED.value
    assert context["inspection_images"] == ["https://images.example.com/inspection-1.jpg"]
    assert context["disclosure_images"] == ["https://images.example.com/disclosure-1.jpg"]
    assert "https://images.example.com/gallery-2.jpg" in context["gallery_images"]
