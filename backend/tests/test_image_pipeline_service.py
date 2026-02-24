from datetime import UTC, datetime

from sqlalchemy import delete, select

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
    Vehicle,
    VehicleImageAsset,
    VehicleImageJob,
    VehicleInspectionImage,
    VehicleInspectionReport,
)
from app.services.image_pipeline_service import (
    ensure_tier2_hero_job,
    ensure_tier3_processing_job,
    resolve_vehicle_display_context,
    sync_marketcheck_source_assets,
)


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


def test_marketing_context_prefers_tier3_gallery_and_tier2_hero() -> None:
    init_db()
    vin = "1HGBH41JXMN109186"
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

        context = resolve_vehicle_display_context(db, vehicle=vehicle, deal_stage=DealState.ACQUIRED)

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
    assert len(context["gallery_images"]) >= 1


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
