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
from app.db.seed import seed
from app.db.session import SessionLocal
from app.models.entities import User
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
