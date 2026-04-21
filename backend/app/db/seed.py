from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.constants import DealState, FundingState
from app.core.security import hash_password
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.entities import (
    BuyerProfile,
    ConfigEntry,
    Deal,
    Document,
    FeatureFlag,
    Notification,
    Shipment,
    User,
)
from app.services.deal_service import transition_deal_state
from app.services.inventory_service import seed_inventory
from app.services.profile_service import apply_quick_match
from app.schemas.profile import QuickMatchRequest


DEFAULT_FEATURE_FLAGS = {
    "QUICK_MATCH_ENABLED": True,
    "FULL_PROFILE_ENABLED": True,
    "AUCTION_AUTO_BID": False,
    "AUTO_CARRIER_BOOKING": False,
    "MULTI_LENDER_WATERFALL": False,
    "EQUITY_ALERTS": False,
    "TIKTOK_CATALOG_FEED": False,
    "RETURN_POLICY_ENABLED": True,
    "DEAL_DESK_AUTO_APPROVE": False,
    "CHROMEDATA_PRIMARY_IMAGES": True,
}

DEFAULT_CONFIG = {
    "margin_threshold": {"value": 1200, "unit": "usd"},
    "service_fee_tiers": {
        "standard": 1295,
        "premier": 1795,
        "concierge": 2495,
    },
    "return_restocking_fee": {"value": 0},
    "geographic_scope": {"states": ["FL"]},
    "sla_hours": {
        "hitl_default": 4,
        "ofac": 0.25,
        "title_exception": 24,
    },
}


def seed() -> None:
    init_db()
    with SessionLocal() as db:
        # Feature flags
        for name, enabled in DEFAULT_FEATURE_FLAGS.items():
            row = db.get(FeatureFlag, name)
            if row:
                row.enabled = enabled
            else:
                db.add(FeatureFlag(name=name, enabled=enabled, description=f"PRD flag: {name}"))

        # Config
        for key, value in DEFAULT_CONFIG.items():
            row = db.get(ConfigEntry, key)
            if row:
                row.value_json = value
            else:
                db.add(ConfigEntry(key=key, value_json=value, description=f"PRD config key: {key}"))

        inserted = seed_inventory(db)

        user = db.scalar(select(User).where(User.email == "buyer@example.com"))
        if not user:
            user = User(
                email="buyer@example.com",
                password_hash=hash_password("BuyerPass123!"),
                first_name="Casey",
                last_name="Buyer",
                phone="+15550001111",
            )
            db.add(user)
            db.flush()

        profile = db.scalar(select(BuyerProfile).where(BuyerProfile.user_id == user.id))
        if not profile:
            profile = BuyerProfile(user_id=user.id)
            db.add(profile)
            db.flush()
            apply_quick_match(
                profile,
                QuickMatchRequest(
                    body_types_included=["SUV", "Truck"],
                    budget_min=22000,
                    budget_max=45000,
                    top_3_priorities=["safety", "tech", "fuel economy"],
                    brands_included=["Ford", "Tesla", "Hyundai"],
                    brands_excluded=["Mitsubishi"],
                    delivery_zip="33445",
                ),
            )

        deal = db.scalar(select(Deal).where(Deal.user_id == user.id).order_by(Deal.created_at.desc()).limit(1))
        if not deal:
            deal = Deal(
                user_id=user.id,
                stage=DealState.MATCHING,
                funding_state=FundingState.CREDIT_APP_PENDING,
            )
            db.add(deal)
            db.flush()

        doc_types = ["service_agreement", "buyer_order", "credit_application"]
        for doc_type in doc_types:
            exists = db.scalar(select(Document).where(Document.deal_id == deal.id, Document.doc_type == doc_type))
            if not exists:
                db.add(Document(deal_id=deal.id, doc_type=doc_type, status="pending", signer_role="buyer"))

        if not db.scalar(select(Notification).where(Notification.user_id == user.id).limit(1)):
            db.add(
                Notification(
                    user_id=user.id,
                    deal_id=deal.id,
                    message="Welcome to Virtual-CarHub. Quick Match is ready for you.",
                )
            )

        if not db.scalar(select(Shipment).where(Shipment.deal_id == deal.id)):
            db.add(
                Shipment(
                    deal_id=deal.id,
                    vin="1FMCU9H9XNUA00001",
                    status="quote_pending",
                    tracking_url=None,
                )
            )

        # Optional delivered scenario for return testing
        delivered = db.scalar(select(Deal).where(Deal.user_id == user.id, Deal.stage == DealState.DELIVERED))
        if not delivered:
            delivered = Deal(
                user_id=user.id,
                stage=DealState.IN_TRANSIT,
                funding_state=FundingState.FULLY_FUNDED,
                selected_vin="5NMS3DAJ9PH000002",
            )
            db.add(delivered)
            db.flush()
            transition_deal_state(
                db,
                deal=delivered,
                new_state=DealState.DELIVERED,
                actor="system",
                reason="seed_delivered_case",
            )
            delivered.delivered_at = datetime.now(UTC) - timedelta(days=2)

        db.commit()
        print("Seed complete")
        print(f"Inserted inventory rows: {inserted}")
        print("Buyer credentials: buyer@example.com / BuyerPass123!")


if __name__ == "__main__":
    seed()
