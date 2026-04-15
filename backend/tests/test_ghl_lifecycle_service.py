import os
import uuid

os.environ["GHL_LIVE_ENABLED"] = "false"

from sqlalchemy import select

from app.api.v1.routers import auth as auth_router
from app.core.config import settings
from app.core.constants import AuctionPlatform, DealState, FundingState
from app.db.seed import seed
from app.db.session import SessionLocal
from app.models.entities import Deal, Notification, OveDetailRequest, OveVehicleDetail, User, Vehicle
from app.schemas.auth import RegisterRequest
from app.services.deal_service import get_or_create_active_deal
from app.services.ghl_lifecycle_service import GHLLifecycleService


def setup_module() -> None:
    seed()


def test_register_persists_ghl_contact_id(monkeypatch) -> None:
    email = f"ghl-register-{uuid.uuid4().hex[:8]}@example.com"
    monkeypatch.setattr(auth_router, "_create_ghl_contact", lambda user: "ghl-contact-123")

    with SessionLocal() as db:
        response = auth_router.register(
            RegisterRequest(
                email=email,
                password="BuyerPass123!",
                first_name="GHL",
                last_name="Tester",
                phone="5615550101",
            ),
            db=db,
        )
        user = db.scalar(select(User).where(User.id == response["data"]["user_id"]))
        assert user is not None
        assert user.ghl_contact_id == "ghl-contact-123"


def test_ghl_webhook_updates_dashboard_state(monkeypatch) -> None:
    lifecycle = GHLLifecycleService()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "buyer@example.com"))
        assert user is not None
        deal = get_or_create_active_deal(db, user.id)
        user.ghl_contact_id = "contact-abc"
        user.is_preapproved = False
        user.preapproved_amount = None
        deal.ghl_contact_id = "contact-abc"
        deal.ghl_opportunity_id = "opp-abc"
        deal.stage = DealState.LEAD
        deal.funding_state = FundingState.CREDIT_APP_PENDING
        deal.selected_vin = None
        db.commit()

        monkeypatch.setattr(settings, "ghl_contact_cf_vch_deal_stage", "cf-stage", raising=False)
        monkeypatch.setattr(settings, "ghl_contact_cf_vch_funding_state", "cf-funding", raising=False)
        monkeypatch.setattr(settings, "ghl_contact_cf_vch_preapproved", "cf-preapproved", raising=False)
        monkeypatch.setattr(settings, "ghl_contact_cf_vch_preapproval_amount", "cf-amount", raising=False)
        monkeypatch.setattr(settings, "ghl_contact_cf_vch_selected_vin", "cf-vin", raising=False)

        result = lifecycle.process_webhook(
            db,
            {
                "type": "OpportunityUpdate",
                "id": "opp-abc",
                "contactId": "contact-abc",
                "pipelineStageId": "stage-docs",
                "customFields": [
                    {"id": "cf-stage", "value": "FUNDING"},
                    {"id": "cf-funding", "value": "PRE_APPROVED"},
                    {"id": "cf-preapproved", "value": "true"},
                    {"id": "cf-amount", "value": "32500"},
                    {"id": "cf-vin", "value": "1M8GDM9AXKP042781"},
                ],
            },
        )
        db.commit()

        refreshed_user = db.get(User, user.id)
        refreshed_deal = db.get(Deal, deal.id)
        notifications = db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
        ).all()

        assert result["updated"] is True
        assert refreshed_user is not None and refreshed_user.is_preapproved is True
        assert refreshed_user.preapproved_amount == 32500.0
        assert refreshed_deal is not None and refreshed_deal.stage == DealState.FUNDING
        assert refreshed_deal.funding_state == FundingState.PRE_APPROVED
        assert refreshed_deal.selected_vin == "1M8GDM9AXKP042781"
        assert any("pre-approved" in notification.message.lower() for notification in notifications)
        assert any("funding" in notification.message.lower() for notification in notifications)


def test_condition_report_completion_creates_notification_and_email(monkeypatch) -> None:
    lifecycle = GHLLifecycleService()
    sent: list[dict] = []
    monkeypatch.setattr(
        "app.services.ghl_lifecycle_service.send_condition_report_ready_email",
        lambda **kwargs: sent.append(kwargs),
    )

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "buyer@example.com"))
        assert user is not None
        deal = get_or_create_active_deal(db, user.id)

        vehicle = db.get(Vehicle, "1M8GDM9AXKP049999")
        if not vehicle:
            vehicle = Vehicle(
                vin="1M8GDM9AXKP049999",
                listing_id=f"ove-{uuid.uuid4().hex[:8]}",
                year=2024,
                make="Ford",
                model="Bronco",
                trim="Outer Banks",
                price_asking=37995,
                source_type="ove",
                available=True,
            )
            db.add(vehicle)
            db.flush()

        detail = db.get(OveVehicleDetail, vehicle.vin)
        if not detail:
            detail = OveVehicleDetail(
                vin=vehicle.vin,
                source_platform=AuctionPlatform.MANHEIM,
            )
            db.add(detail)
        detail.images_json = [{"url": "https://cdn.example.com/bronco.jpg", "role": "gallery"}]
        detail.condition_report_json = {
            "metadata": {
                "report_link": {
                    "href": "https://example.com/reports/bronco",
                }
            }
        }

        request = OveDetailRequest(
            vin=vehicle.vin,
            source_platform=AuctionPlatform.MANHEIM,
            metadata_json={"user_id": user.id, "deal_id": deal.id},
        )
        db.add(request)
        db.flush()

        lifecycle.handle_condition_report_completion(
            db,
            detail=detail,
            completed_requests=[request],
        )
        db.flush()

        notifications = db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
        ).all()

        assert any(vehicle.vin in notification.message for notification in notifications)
        assert len(sent) == 1
        assert sent[0]["vin"] == vehicle.vin
        assert sent[0]["user"].id == user.id
