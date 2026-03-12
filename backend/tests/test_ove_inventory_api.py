from sqlalchemy import delete

from app.api.v1.routers.inventory import get_inventory_vehicle
from app.api.v1.routers.inventory_ove import (
    ingest_ove,
    pending_ove_detail_requests,
    push_ove_detail,
    request_ove_detail,
)
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.entities import OveDetailRequest, OveVehicleDetail, Vehicle
from app.schemas.ove_inventory import (
    OveBulkIngestRequest,
    OveDetailPushRequest,
    OveDetailRequestEnqueueRequest,
    OveImagePayload,
    OveListingSnapshot,
    OveVehicleIngestItem,
)


def test_ove_ingest_request_pending_and_detail_contract() -> None:
    init_db()
    vin = "1HGCM82633A004352"

    with SessionLocal() as db:
        db.execute(delete(OveDetailRequest))
        db.execute(delete(OveVehicleDetail))
        db.execute(delete(Vehicle).where(Vehicle.vin == vin))
        db.commit()

        ingest_response = ingest_ove(
            OveBulkIngestRequest(
                vehicles=[
                    OveVehicleIngestItem(
                        vin=vin,
                        listing_id="ove-123",
                        year=2023,
                        make="Honda",
                        model="Accord",
                        trim="EX",
                        body_type="Sedan",
                        price_asking=23995,
                        location_zip="33445",
                        location_state="fl",
                        source_url="https://example.com/ove/accord",
                        images=[
                            "https://images.example.com/accord-1.jpg",
                            "https://images.example.com/accord-2.jpg",
                        ],
                        features_raw=["Adaptive Cruise", "CarPlay"],
                        features_normalized={"fuel_type": "Gasoline", "transmission": "CVT"},
                    )
                ],
                sync_metadata={"batch_id": "ove-batch-1", "crawler": "standalone-ove"},
            ),
            db=db,
        )
        assert ingest_response["status"] == "ok"
        assert ingest_response["data"]["source"] == "ove"
        assert ingest_response["data"]["inserted"] == 1

        enqueue_response = request_ove_detail(
            vin,
            OveDetailRequestEnqueueRequest(
                request_source="scraper",
                requested_by="ove-sync",
                reason="Need auction detail layout",
                metadata={"job_id": "detail-job-1"},
            ),
            db=db,
        )
        assert enqueue_response["status"] == "ok"
        request_id = enqueue_response["data"]["request_id"]

        pending_response = pending_ove_detail_requests(limit=10, db=db)
        assert pending_response["status"] == "ok"
        assert pending_response["data"]["count"] >= 1
        assert any(item["vin"] == vin for item in pending_response["data"]["items"])

        detail_response = push_ove_detail(
            vin,
            OveDetailPushRequest(
                images=[
                    OveImagePayload(
                        url="https://images.example.com/accord-hero.jpg",
                        role="hero",
                        display_order=0,
                        is_primary=True,
                    ),
                    OveImagePayload(
                        url="https://images.example.com/accord-dash.jpg",
                        role="gallery",
                        display_order=1,
                    ),
                ],
                condition_report={
                    "grade": "4.2",
                    "announcements": ["Structural damage disclosed"],
                },
                seller_comments="Runs and drives well.",
                listing_snapshot=OveListingSnapshot(
                    title="2023 Honda Accord EX",
                    subtitle="LaneWatch, Clean Carfax",
                    badges=[{"label": "Buy Now"}],
                    hero_facts=[{"label": "Odometer", "value": "24,120"}],
                    sections=[
                        {
                            "id": "announcements",
                            "title": "Announcements",
                            "layout": "list",
                            "items": [{"label": "Structural damage disclosed"}],
                        }
                    ],
                    icons=[{"name": "engine", "value": "1.5T"}],
                    page_url="https://example.com/ove/accord/detail",
                    screenshot_refs=["s3://bucket/accord-page.png"],
                    raw_html_ref="s3://bucket/accord-page.html",
                ),
                sync_metadata={"job_id": "detail-job-1"},
            ),
            db=db,
        )
        assert detail_response["status"] == "ok"
        assert detail_response["data"]["vin"] == vin
        assert request_id in detail_response["data"]["completed_request_ids"]

        vehicle_detail = get_inventory_vehicle(vin=vin, db=db)
        assert vehicle_detail["status"] == "ok"
        assert vehicle_detail["data"]["ove_detail"]["listing_snapshot"]["title"] == "2023 Honda Accord EX"
        assert vehicle_detail["data"]["seller_comments"] == "Runs and drives well."
        assert vehicle_detail["data"]["condition_report"]["grade"] == "4.2"


def test_ove_detail_request_deduplicates_pending_rows() -> None:
    init_db()
    vin = "1HGCM82633A004353"
    with SessionLocal() as db:
        db.execute(delete(OveDetailRequest).where(OveDetailRequest.vin == vin))
        db.commit()

        first = request_ove_detail(vin, OveDetailRequestEnqueueRequest(), db=db)
        second = request_ove_detail(vin, OveDetailRequestEnqueueRequest(), db=db)

        assert first["status"] == "ok"
        assert second["status"] == "ok"
        assert second["data"]["deduplicated"] is True
        assert first["data"]["request_id"] == second["data"]["request_id"]


def test_ove_full_snapshot_marks_missing_rows_sold() -> None:
    init_db()
    vin_keep = "1HGCM82633A004354"
    vin_stale = "1HGCM82633A004355"

    with SessionLocal() as db:
        db.execute(delete(OveDetailRequest).where(OveDetailRequest.vin.in_([vin_keep, vin_stale])))
        db.execute(delete(OveVehicleDetail).where(OveVehicleDetail.vin.in_([vin_keep, vin_stale])))
        db.execute(delete(Vehicle).where(Vehicle.vin.in_([vin_keep, vin_stale])))
        db.commit()

        first = ingest_ove(
            OveBulkIngestRequest(
                vehicles=[
                    OveVehicleIngestItem(
                        vin=vin_keep,
                        listing_id="ove-keep-1",
                        year=2023,
                        make="Honda",
                        model="Civic",
                        price_asking=21000,
                        location_zip="33445",
                        location_state="FL",
                    ),
                    OveVehicleIngestItem(
                        vin=vin_stale,
                        listing_id="ove-stale-1",
                        year=2022,
                        make="Toyota",
                        model="Camry",
                        price_asking=20000,
                        location_zip="33446",
                        location_state="FL",
                    ),
                ],
                sync_metadata={"batch_id": "snap-1", "full_snapshot": True},
            ),
            db=db,
        )
        assert first["status"] == "ok"

        second = ingest_ove(
            OveBulkIngestRequest(
                vehicles=[
                    OveVehicleIngestItem(
                        vin=vin_keep,
                        listing_id="ove-keep-1",
                        year=2023,
                        make="Honda",
                        model="Civic",
                        price_asking=21500,
                        location_zip="33445",
                        location_state="FL",
                    )
                ],
                sync_metadata={"batch_id": "snap-2", "full_snapshot": True},
            ),
            db=db,
        )
        assert second["status"] == "ok"
        assert second["data"]["marked_sold"] == 1

        keep = db.get(Vehicle, vin_keep)
        stale = db.get(Vehicle, vin_stale)
        assert keep is not None and keep.available is True
        assert stale is not None and stale.available is False
        assert stale.features_normalized["status"] == "Sold"
