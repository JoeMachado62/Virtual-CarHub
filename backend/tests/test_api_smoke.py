import os

os.environ["GHL_LIVE_ENABLED"] = "false"
os.environ["MARKETCHECK_LIVE_ENABLED"] = "false"
os.environ["DOCUSIGN_LIVE_ENABLED"] = "false"
os.environ["TELNYX_LIVE_ENABLED"] = "false"

from sqlalchemy import select

from app.api.v1.routers import admin as admin_router
from app.api.v1.routers import auth as auth_router
from app.api.v1.routers import me as me_router
from app.api.v1.routers import returns as returns_router
from app.core.constants import DealState, FundingState, InventorySourceType
from app.db.seed import seed
from app.db.session import SessionLocal
from app.models.entities import OveDetailRequest, User, Vehicle
from app.schemas.auth import LoginRequest
from app.schemas.profile import QuickMatchRequest
from app.schemas.returns import ConfirmReceiptRequest, InitiateReturnRequest, RefundRequest
from app.services.deal_service import get_or_create_active_deal


def _buyer(db) -> User:
    user = db.scalar(select(User).where(User.email == "buyer@example.com"))
    assert user is not None
    return user


def setup_module() -> None:
    seed()


def test_quick_match_and_recommendations() -> None:
    with SessionLocal() as db:
        login = auth_router.login(
            LoginRequest(email="buyer@example.com", password="BuyerPass123!"),
            db=db,
        )
        assert login["status"] == "ok"
        assert login["data"]["access_token"]

        user = _buyer(db)
        deal = get_or_create_active_deal(db, user.id)
        quick_match = me_router.post_quick_match(
            QuickMatchRequest(
                body_types_included=["SUV"],
                budget_min=20000,
                budget_max=45000,
                top_3_priorities=["safety", "tech", "fuel economy"],
                brands_included=["Ford", "Tesla"],
                brands_excluded=["Mitsubishi"],
                delivery_zip="33445",
            ),
            db=db,
            current_user=user,
            current_deal=deal,
        )
        assert quick_match["status"] == "ok"
        assert quick_match["data"]["match_count"] > 0

        recommendations = me_router.get_recommendations(db=db, current_deal=deal)
        assert recommendations["status"] == "ok"
        assert len(recommendations["data"]) > 0


def test_quick_match_does_not_rewind_later_stage() -> None:
    with SessionLocal() as db:
        user = _buyer(db)
        deal = get_or_create_active_deal(db, user.id)
        deal.stage = DealState.VEHICLE_SELECTED
        db.commit()

        quick_match = me_router.post_quick_match(
            QuickMatchRequest(
                body_types_included=["SUV"],
                budget_min=20000,
                budget_max=45000,
                top_3_priorities=["safety", "tech", "fuel economy"],
                brands_included=["Ford", "Tesla"],
                brands_excluded=["Mitsubishi"],
                delivery_zip="33445",
            ),
            db=db,
            current_user=user,
            current_deal=deal,
        )

        assert quick_match["status"] == "ok"
        assert quick_match["data"]["match_count"] > 0
        assert deal.stage == DealState.VEHICLE_SELECTED


def test_buyer_can_request_ove_condition_report_when_preapproved() -> None:
    with SessionLocal() as db:
        user = _buyer(db)
        deal = get_or_create_active_deal(db, user.id)
        deal.funding_state = FundingState.PRE_APPROVED

        vehicle = db.get(Vehicle, "1M8GDM9AXKP042788")
        if not vehicle:
            vehicle = Vehicle(
                vin="1M8GDM9AXKP042788",
                listing_id="ove-test-1",
                year=2024,
                make="Ford",
                model="Bronco",
                trim="Outer Banks",
                price_asking=37995,
                source_type=InventorySourceType.OVE.value,
                available=True,
            )
            db.add(vehicle)
        else:
            vehicle.source_type = InventorySourceType.OVE.value
        db.commit()

        detail = me_router.request_vehicle_condition_report(
            vin=vehicle.vin,
            db=db,
            current_user=user,
            current_deal=deal,
        )
        db.commit()

        assert detail["status"] == "ok"
        assert detail["data"]["eligible"] is True
        assert detail["data"]["queued"] is True

        queued = db.scalar(select(OveDetailRequest).where(OveDetailRequest.vin == vehicle.vin))
        assert queued is not None
        assert queued.request_source == "buyer_portal"

        deal_payload = me_router.get_deal(current_deal=deal)
        assert deal_payload["status"] == "ok"
        assert deal_payload["data"]["condition_report_eligible"] is True


def test_garage_save_and_acquisition_enqueue_ove_detail_refresh() -> None:
    with SessionLocal() as db:
        user = _buyer(db)
        deal = get_or_create_active_deal(db, user.id)

        vin_saved = "1M8GDM9AXKP042781"
        vin_acquire = "1M8GDM9AXKP042782"
        for vin in [vin_saved, vin_acquire]:
            existing = db.get(Vehicle, vin)
            if not existing:
                db.add(
                    Vehicle(
                        vin=vin,
                        listing_id=f"ove-{vin}",
                        year=2024,
                        make="Ford",
                        model="Bronco",
                        trim="Outer Banks",
                        price_asking=37995,
                        source_type=InventorySourceType.OVE.value,
                        available=True,
                    )
                )
            else:
                existing.source_type = InventorySourceType.OVE.value
                existing.available = True
            queued = db.scalar(select(OveDetailRequest).where(OveDetailRequest.vin == vin))
            if queued:
                db.delete(queued)
        db.commit()

        saved = me_router.add_to_garage(
            vin=vin_saved,
            db=db,
            current_user=user,
            current_deal=deal,
        )
        db.commit()

        assert saved["status"] == "ok"
        assert saved["data"]["ove_detail_refresh"]["queued"] is True
        queued_saved = db.scalar(select(OveDetailRequest).where(OveDetailRequest.vin == vin_saved))
        assert queued_saved is not None
        assert queued_saved.reason == f"garage_saved:{deal.id}"

        acquired = me_router.start_garage_acquisition(
            vin=vin_acquire,
            db=db,
            current_user=user,
            current_deal=deal,
        )
        db.commit()

        assert acquired["status"] == "ok"
        assert acquired["data"]["ove_detail_refresh"]["queued"] is True
        queued_acquire = db.scalar(select(OveDetailRequest).where(OveDetailRequest.vin == vin_acquire))
        assert queued_acquire is not None
        assert queued_acquire.reason == f"garage_acquisition_started:{deal.id}"


def test_return_flow_internal_endpoint() -> None:
    with SessionLocal() as db:
        deals_response = admin_router.get_deals(db=db)
        delivered = next((row for row in deals_response["data"] if row["stage"] == "DELIVERED"), None)
        assert delivered is not None

        initiate = returns_router.initiate(
            delivered["id"],
            InitiateReturnRequest(reason="Did not like handling", buyer_transport_responsibility=True),
            db=db,
        )
        assert initiate["status"] == "ok"
        assert initiate["data"]["state"] == "RETURN_PENDING"

        confirm_receipt = returns_router.confirm_receipt(
            delivered["id"],
            ConfirmReceiptRequest(damage_deduction=120.0),
            db=db,
        )
        assert confirm_receipt["status"] == "ok"

        refund = returns_router.refund(
            delivered["id"],
            RefundRequest(restocking_fee=0.0, damage_deduction=120.0),
            db=db,
        )
        assert refund["status"] == "ok"
        assert refund["data"]["refund_amount"] >= 0
