import os

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import delete, func

# Hard guard against running these tests against a non-throwaway database.
# These tests use db.execute(delete(OveDetailRequest)) and seed fixture VINs
# directly via SessionLocal(), which means they will WIPE THE LIVE QUEUE if
# pointed at production. We allow only sqlite or an explicitly-named test DB.
_db_url = os.environ.get("DATABASE_URL", "")
if _db_url and "sqlite" not in _db_url and "test" not in _db_url.lower():
    raise RuntimeError(
        f"Refusing to run destructive OVE inventory tests against DATABASE_URL={_db_url!r}. "
        "These tests truncate ove_detail_requests. Point DATABASE_URL at a sqlite file or "
        "a database whose name contains 'test' before running this suite."
    )

from app.api.v1.routers.inventory import get_inventory_vehicle
from app.api.v1.routers.inventory_ove import (
    claim_ove_detail,
    complete_ove_detail,
    fail_ove_detail,
    heartbeat_ove_detail,
    ingest_ove,
    pending_ove_detail_requests,
    push_ove_detail,
    request_ove_detail,
    terminal_ove_detail,
)
from app.core.constants import OveDetailRequestStatus
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.entities import OveDetailRequest, OveVehicleDetail, Vehicle
from app.schemas.ove_inventory import (
    OveBulkIngestRequest,
    OveDetailClaimRequest,
    OveDetailCompleteRequest,
    OveDetailFailRequest,
    OveDetailHeartbeatRequest,
    OveDetailPushRequest,
    OveDetailRequestEnqueueRequest,
    OveDetailTerminalRequest,
    OveImagePayload,
    OveListingSnapshot,
    OveVehicleIngestItem,
)
from app.services import ove_inventory_service


def test_ove_ingest_request_pending_and_detail_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    init_db()
    vin = "1HGCM82633A004352"

    class _StubNHTSAClient:
        def decode_vin(self, _vin):
            class _Decoded:
                year = None
            return _Decoded()

    monkeypatch.setattr("app.api.v1.routers.inventory.NHTSAClient", _StubNHTSAClient)

    with SessionLocal() as db:
        # Clean slate: remove ALL OVE vehicles so safety guards don't trigger
        # when we ingest only 1 test vehicle.
        db.execute(delete(OveDetailRequest))
        db.execute(delete(OveVehicleDetail))
        db.execute(delete(Vehicle).where(func.lower(Vehicle.source_type) == "ove"))
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
                    "overall_grade": "4.2",
                    "announcements": ["Structural damage disclosed"],
                    "metadata": {
                        "report_link": {
                            "href": "http://content.liquidmotors.com/IR/15614/38020971.html",
                            "title": "4.2",
                        },
                        "announcementsEnrichment": {
                            "announcements": ["Structural damage disclosed"],
                        },
                    },
                    "vehicle_history": {
                        "owners": 1,
                        "accidents": 0,
                        "engine_starts": True,
                        "drivable": True,
                    },
                    "damage_items": [],
                    "damage_summary": {"total_items": 0, "structural_issue": False},
                    "tire_depths": {
                        "lf": {"position_label": "LF", "tread_depth": "6/32"},
                        "rf": {"position_label": "RF", "tread_depth": "6/32"},
                        "lr": {"position_label": "LR", "tread_depth": "7/32"},
                        "rr": {"position_label": "RR", "tread_depth": "7/32"},
                    },
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

        vehicle_detail = get_inventory_vehicle(identifier=vin, db=db, current_user=None)
        assert vehicle_detail["status"] == "ok"
        assert vehicle_detail["data"]["ove_detail"]["listing_snapshot"]["title"] == "2023 Honda Accord EX"
        assert vehicle_detail["data"]["seller_comments"] == "Runs and drives well."
        assert vehicle_detail["data"]["condition_report"]["overall_grade"] == "4.2"
        assert vehicle_detail["data"]["condition_report_grade"] == "4.2"
        assert vehicle_detail["data"]["condition_report_url"] == "http://content.liquidmotors.com/IR/15614/38020971.html"


def test_ove_detail_push_request_rejects_incomplete_condition_report_contract() -> None:
    with pytest.raises(ValidationError) as excinfo:
        OveDetailPushRequest(
            images=[
                OveImagePayload(
                    url="https://images.example.com/accord-hero.jpg",
                    role="hero",
                    display_order=0,
                    is_primary=True,
                ),
            ],
            condition_report={
                "overall_grade": "4.2",
                "damage_items": [],
                "vehicle_history": {"owners": 1},
                "tire_depths": {},
            },
        )

    message = str(excinfo.value)
    assert "metadata.report_link.href is required" in message
    assert "vehicle_history.owners and .accidents are required" in message
    assert "tire_depths must include lf, rf, lr, and rr" in message


def test_ove_detail_push_request_normalizes_legacy_grade_and_report_link_fields() -> None:
    payload = OveDetailPushRequest(
        images=[
            OveImagePayload(
                url="https://images.example.com/accord-hero.jpg",
                role="hero",
                display_order=0,
                is_primary=True,
            ),
        ],
        condition_report={
            "grade": "3.5",
            "condition_report_url": "http://content.liquidmotors.com/IR/15614/38020972.html",
            "metadata": {
                "announcementsEnrichment": {
                    "announcements": ["Open Recall"],
                }
            },
            "vehicle_history": {
                "owners": "2",
                "accidents": "1",
            },
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

    assert payload.condition_report["overall_grade"] == "3.5"
    assert payload.condition_report["metadata"]["report_link"]["href"] == "http://content.liquidmotors.com/IR/15614/38020972.html"
    assert payload.condition_report["announcements"] == ["Open Recall"]


def test_ove_detail_push_request_accepts_liquid_motors_equipment_and_empty_mirrored_announcements() -> None:
    payload = OveDetailPushRequest(
        images=[
            OveImagePayload(
                url="https://assets.cai-media-management.com/example-photo-1.jpg",
                role="hero",
                display_order=0,
                is_primary=True,
            ),
            OveImagePayload(
                url="https://assets.cai-media-management.com/example-photo-2.jpg",
                role="gallery",
                display_order=1,
            ),
        ],
        condition_report={
            "overall_grade": "4.6",
            "equipment_features": [
                "BLUETOOTH HANDS FREE MOBILE",
                "NAVIGATION SYSTEM",
                "POWER MOONROOF",
            ],
            "installed_equipment": [],
            "high_value_options": [],
            "announcements": [],
            "metadata": {
                "report_link": {"href": "http://content.liquidmotors.com/IR/15614/38020972.html"},
                "announcementsEnrichment": {"announcements": []},
            },
            "vehicle_history": {
                "owners": 1,
                "accidents": 0,
                "drivable": True,
                "engine_starts": True,
            },
            "damage_items": [],
            "damage_summary": {"total_items": 0},
            "tire_depths": {
                "driver_front": {"position_label": "Driver Front", "tread_depth": "7/32"},
                "lf": {"position_label": "LF", "tread_depth": "7/32"},
                "rf": {"position_label": "RF", "tread_depth": "7/32"},
                "lr": {"position_label": "LR", "tread_depth": "6/32"},
                "rr": {"position_label": "RR", "tread_depth": "6/32"},
            },
        },
    )

    assert payload.condition_report["equipment_features"] == [
        "BLUETOOTH HANDS FREE MOBILE",
        "NAVIGATION SYSTEM",
        "POWER MOONROOF",
    ]
    assert payload.condition_report["metadata"]["announcementsEnrichment"]["announcements"] == []
    assert payload.condition_report["announcements"] == []


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


def test_ove_full_snapshot_marks_missing_rows_sold(monkeypatch: pytest.MonkeyPatch) -> None:
    init_db()

    vin_keep = "1HGCM82633A004354"
    vin_stale = "1HGCM82633A004355"

    with SessionLocal() as db:
        # Clean slate: remove all OVE vehicles so counts are predictable
        db.execute(delete(OveDetailRequest))
        db.execute(delete(OveVehicleDetail))
        db.execute(delete(Vehicle).where(func.lower(Vehicle.source_type) == "ove"))
        db.execute(delete(Vehicle).where(Vehicle.vin.in_([vin_keep, vin_stale])))
        db.commit()

        # First ingest: 2 vehicles (no existing, so safety guards skip)
        first = ove_inventory_service.ingest_ove_inventory(
            db,
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
                sync_metadata={"batch_id": "snap-1"},
            ),
        )
        db.commit()
        assert first.inserted == 2

        # Second ingest: only vin_keep; override ratio to 0 so 1-vs-2 passes
        second = ove_inventory_service.ingest_ove_inventory(
            db,
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
                sync_metadata={"batch_id": "snap-2"},
            ),
            min_count_override=0,
            min_ratio_override=0.0,
        )
        db.commit()
        # The second ingest marks the 2 vehicles from first ingest as
        # unavailable, then upserts the 1 incoming vehicle as available.
        assert second.marked_sold == 2

        # Expire cached ORM state to see the DB reality after bulk upsert
        db.expire_all()
        keep = db.get(Vehicle, vin_keep)
        stale = db.get(Vehicle, vin_stale)
        assert keep is not None and keep.available is True
        assert stale is not None and stale.available is False


# ---------------------------------------------------------------------------
# Lease-based claim queue tests
# ---------------------------------------------------------------------------


def _seed_request(db, vin: str) -> str:
    response = request_ove_detail(vin, OveDetailRequestEnqueueRequest(), db=db)
    return response["data"]["request_id"]


def _wipe_requests(db, vins: list[str]) -> None:
    db.execute(delete(OveDetailRequest).where(OveDetailRequest.vin.in_(vins)))
    db.commit()


def test_detail_claim_route_is_not_shadowed_by_dynamic_vin_route() -> None:
    """Regression: POST /detail/claim must resolve to claim_ove_detail, not
    push_ove_detail with vin='claim'. The static lease-queue routes have to
    be declared BEFORE the dynamic /detail/{vin} catch-all.
    """
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.main import app

    init_db()
    with SessionLocal() as db:
        db.execute(delete(OveDetailRequest))
        db.commit()

    client = TestClient(app)
    response = client.post(
        "/v1/inventory/ove/detail/claim",
        headers={"X-Service-Token": settings.service_token},
        json={"worker_id": "route-order-test", "limit": 1, "lease_seconds": 60},
    )
    # The bug returned 422 "VIN must be 17 characters" because the request was
    # routed into push_ove_detail. A correctly-routed claim returns 200 with
    # an empty items list when the queue is empty.
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ok"
    assert body["data"]["count"] == 0
    assert body["data"]["items"] == []


def test_concurrent_claimers_do_not_share_request_ids() -> None:
    init_db()
    vins = [f"1HGCM82633A0050{idx:02d}" for idx in range(4)]
    with SessionLocal() as db:
        # Wipe the entire active queue so the assertion is deterministic
        # regardless of any leftover rows from earlier tests.
        db.execute(delete(OveDetailRequest))
        db.commit()
        request_ids = {_seed_request(db, vin) for vin in vins}
        db.commit()

        first = claim_ove_detail(
            OveDetailClaimRequest(worker_id="worker-A", limit=10, lease_seconds=600),
            db=db,
        )
        second = claim_ove_detail(
            OveDetailClaimRequest(worker_id="worker-B", limit=10, lease_seconds=600),
            db=db,
        )

        first_ids = {item["request_id"] for item in first["data"]["items"]}
        second_ids = {item["request_id"] for item in second["data"]["items"]}

        assert first_ids == request_ids
        assert second_ids == set()
        assert first_ids.isdisjoint(second_ids)
        for item in first["data"]["items"]:
            row = db.get(OveDetailRequest, item["request_id"])
            assert row.status == OveDetailRequestStatus.CLAIMED
            assert row.leased_to == "worker-A"
            assert row.attempts == 1


def test_expired_leases_are_reclaimable() -> None:
    init_db()
    vin = "1HGCM82633A005100"
    with SessionLocal() as db:
        _wipe_requests(db, [vin])
        request_id = _seed_request(db, vin)
        db.commit()

        first = claim_ove_detail(
            OveDetailClaimRequest(worker_id="worker-A", limit=5, lease_seconds=600),
            db=db,
        )
        assert any(item["request_id"] == request_id for item in first["data"]["items"])

        # Force the lease to be expired in the past.
        row = db.get(OveDetailRequest, request_id)
        row.lease_expires_at = datetime.now(UTC) - timedelta(seconds=60)
        db.commit()

        second = claim_ove_detail(
            OveDetailClaimRequest(worker_id="worker-B", limit=5, lease_seconds=600),
            db=db,
        )
        ids = {item["request_id"] for item in second["data"]["items"]}
        assert request_id in ids
        row = db.get(OveDetailRequest, request_id)
        assert row.leased_to == "worker-B"
        assert row.attempts == 2


def test_completed_requests_do_not_reappear_in_claims() -> None:
    init_db()
    vin = "1HGCM82633A005200"
    with SessionLocal() as db:
        _wipe_requests(db, [vin])
        request_id = _seed_request(db, vin)
        db.commit()

        claim_ove_detail(
            OveDetailClaimRequest(worker_id="worker-A", limit=5, lease_seconds=600),
            db=db,
        )
        complete_ove_detail(
            request_id,
            OveDetailCompleteRequest(worker_id="worker-A", result="success"),
            db=db,
        )

        again = claim_ove_detail(
            OveDetailClaimRequest(worker_id="worker-B", limit=10, lease_seconds=600),
            db=db,
        )
        ids = {item["request_id"] for item in again["data"]["items"]}
        assert request_id not in ids


def test_terminal_requests_do_not_reappear() -> None:
    init_db()
    vin = "1HGCM82633A005300"
    with SessionLocal() as db:
        _wipe_requests(db, [vin])
        request_id = _seed_request(db, vin)
        db.commit()

        claim_ove_detail(
            OveDetailClaimRequest(worker_id="worker-A", limit=5, lease_seconds=600),
            db=db,
        )
        terminal_ove_detail(
            request_id,
            OveDetailTerminalRequest(
                worker_id="worker-A",
                reason="vehicle_missing_on_vps",
                message="Vehicle not found on VPS when posting detail result",
            ),
            db=db,
        )

        # Even when the lease is forced to be expired, terminal rows must
        # never come back to the queue.
        row = db.get(OveDetailRequest, request_id)
        assert row.status == OveDetailRequestStatus.TERMINAL
        row.lease_expires_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()

        again = claim_ove_detail(
            OveDetailClaimRequest(worker_id="worker-B", limit=10, lease_seconds=600),
            db=db,
        )
        ids = {item["request_id"] for item in again["data"]["items"]}
        assert request_id not in ids


def test_failed_requests_only_reappear_after_next_retry_at() -> None:
    init_db()
    vin = "1HGCM82633A005400"
    with SessionLocal() as db:
        _wipe_requests(db, [vin])
        request_id = _seed_request(db, vin)
        db.commit()

        claim_ove_detail(
            OveDetailClaimRequest(worker_id="worker-A", limit=5, lease_seconds=600),
            db=db,
        )
        fail_ove_detail(
            request_id,
            OveDetailFailRequest(
                worker_id="worker-A",
                error_category="browser_error",
                error_message="Unable to open detail page",
                retry_after_seconds=3600,
            ),
            db=db,
        )

        # Inside the backoff window — must NOT be returned.
        before = claim_ove_detail(
            OveDetailClaimRequest(worker_id="worker-B", limit=10, lease_seconds=600),
            db=db,
        )
        ids_before = {item["request_id"] for item in before["data"]["items"]}
        assert request_id not in ids_before

        # Move next_retry_at into the past and re-claim.
        row = db.get(OveDetailRequest, request_id)
        row.next_retry_at = datetime.now(UTC) - timedelta(seconds=10)
        db.commit()

        after = claim_ove_detail(
            OveDetailClaimRequest(worker_id="worker-B", limit=10, lease_seconds=600),
            db=db,
        )
        ids_after = {item["request_id"] for item in after["data"]["items"]}
        assert request_id in ids_after
        row = db.get(OveDetailRequest, request_id)
        assert row.leased_to == "worker-B"
        assert row.attempts == 2


def test_complete_rejected_for_non_owning_worker() -> None:
    init_db()
    vin = "1HGCM82633A005500"
    with SessionLocal() as db:
        _wipe_requests(db, [vin])
        request_id = _seed_request(db, vin)
        db.commit()

        claim_ove_detail(
            OveDetailClaimRequest(worker_id="worker-A", limit=5, lease_seconds=600),
            db=db,
        )

        with pytest.raises(HTTPException) as exc_info:
            complete_ove_detail(
                request_id,
                OveDetailCompleteRequest(worker_id="worker-B"),
                db=db,
            )
        assert exc_info.value.status_code == 409


def test_heartbeat_extends_lease_for_owning_worker() -> None:
    init_db()
    vin = "1HGCM82633A005600"
    with SessionLocal() as db:
        _wipe_requests(db, [vin])
        request_id = _seed_request(db, vin)
        db.commit()

        claim_ove_detail(
            OveDetailClaimRequest(worker_id="worker-A", limit=5, lease_seconds=120),
            db=db,
        )
        original = db.get(OveDetailRequest, request_id).lease_expires_at

        heartbeat_ove_detail(
            request_id,
            OveDetailHeartbeatRequest(worker_id="worker-A", lease_seconds=900),
            db=db,
        )
        extended = db.get(OveDetailRequest, request_id).lease_expires_at
        assert extended > original


def test_detail_push_clears_lease_and_completes_claimed_request() -> None:
    init_db()
    vin = "1HGCM82633A005700"
    with SessionLocal() as db:
        db.execute(delete(OveDetailRequest))
        db.execute(delete(OveVehicleDetail))
        db.execute(delete(Vehicle).where(func.lower(Vehicle.source_type) == "ove"))
        db.execute(delete(Vehicle).where(Vehicle.vin == vin))
        db.commit()

        ingest_ove(
            OveBulkIngestRequest(
                vehicles=[
                    OveVehicleIngestItem(
                        vin=vin,
                        listing_id="ove-claim-1",
                        year=2023,
                        make="Honda",
                        model="Accord",
                        price_asking=22000,
                        location_zip="33445",
                        location_state="FL",
                    )
                ],
                sync_metadata={"batch_id": "claim-test"},
            ),
            db=db,
        )
        request_id = _seed_request(db, vin)
        claim_ove_detail(
            OveDetailClaimRequest(worker_id="worker-A", limit=5, lease_seconds=600),
            db=db,
        )

        push_ove_detail(
            vin,
            OveDetailPushRequest(
                images=[OveImagePayload(url="https://example.com/img.jpg")],
                listing_snapshot=OveListingSnapshot(title="2023 Honda Accord"),
            ),
            db=db,
        )

        row = db.get(OveDetailRequest, request_id)
        assert row.status == OveDetailRequestStatus.COMPLETED
        assert row.leased_to is None
        assert row.lease_expires_at is None
        assert row.completed_at is not None
