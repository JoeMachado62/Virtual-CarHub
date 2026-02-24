from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.api.v1.routers.inventory import get_inventory_vehicle, search_inventory
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.entities import Vehicle
from app.services.inventory_service import (
    ingest_marketcheck_inventory,
    seed_inventory,
    upsert_vehicle_with_source_priority,
)


class StubMarketCheckClient:
    def __init__(self, listings: list[dict]) -> None:
        self.live = True
        self._listings = listings

    def search_inventory(self, params: dict) -> dict:
        _ = params
        return {"listings": self._listings}


def test_ingest_marketcheck_inventory_inserts_rows() -> None:
    init_db()
    listings = [
        {
            "id": "1HGBH41JXMN109186-stub",
            "vin": "1HGBH41JXMN109186",
            "price": 24500,
            "miles": 41123,
            "build": {
                "year": 2021,
                "make": "Honda",
                "model": "Civic",
                "trim": "EX",
                "body_type": "Sedan",
                "engine": "I4",
                "drivetrain": "FWD",
                "cylinders": 4,
            },
            "dealer": {"state": "FL", "zip": "33445"},
            "media": {
                "photo_links": ["https://example.com/civic-original.jpg"],
                "photo_links_cached": ["https://cached.example.com/civic.jpg"],
            },
            "extra": {"features": ["CarPlay", "Blind Spot"]},
        },
        {
            "id": "5YJ3E1EA7KF317000-stub",
            "vin": "5YJ3E1EA7KF317000",
            "price": 28999,
            "miles": 35421,
            "build": {
                "year": 2019,
                "make": "Tesla",
                "model": "Model 3",
                "trim": "Long Range",
                "body_type": "Sedan",
                "engine": "Electric",
                "drivetrain": "AWD",
                "cylinders": 0,
            },
            "dealer": {"state": "TX", "zip": "75001"},
        },
    ]
    client = StubMarketCheckClient(listings)

    with SessionLocal() as db:
        db.execute(delete(Vehicle).where(Vehicle.vin.in_(["1HGBH41JXMN109186", "5YJ3E1EA7KF317000"])))
        db.commit()

        report = ingest_marketcheck_inventory(db, client=client, limit=2, start=0)
        db.commit()

        rows = db.scalars(
            select(Vehicle).where(Vehicle.vin.in_(["1HGBH41JXMN109186", "5YJ3E1EA7KF317000"]))
        ).all()

    assert report.inserted == 2
    assert report.updated == 0
    assert report.skipped_priority == 0
    assert len(rows) == 2
    assert all(row.source_type == "marketcheck" for row in rows)
    civic = next((row for row in rows if row.vin == "1HGBH41JXMN109186"), None)
    assert civic is not None
    assert civic.images == ["https://cached.example.com/civic.jpg"]


def test_source_priority_auction_wins_against_marketcheck_update() -> None:
    existing = Vehicle(
        vin="JM3KFBCM1S0811107",
        listing_id="auction-001",
        year=2025,
        make="Mazda",
        model="CX-5",
        price_asking=35500,
        source_type="auction",
        available=True,
    )
    incoming = {
        "vin": "JM3KFBCM1S0811107",
        "year": 2025,
        "make": "Mazda",
        "model": "CX-5",
        "price_asking": 31363,
        "last_seen_active": datetime.now(UTC),
        "available": True,
    }

    action = upsert_vehicle_with_source_priority(
        existing=existing,
        incoming=incoming,
        incoming_source="marketcheck",
    )

    assert action == "skipped_priority"
    assert existing.price_asking == 35500
    assert existing.source_type == "auction"


def test_inventory_search_and_detail_contract() -> None:
    init_db()
    with SessionLocal() as db:
        seed_inventory(db)
        db.commit()

        response = search_inventory(
            q=None,
            make=None,
            model=None,
            body_type="SUV",
            source_type=None,
            state=None,
            min_price=None,
            max_price=None,
            min_year=None,
            max_year=None,
            min_miles=None,
            max_miles=None,
            has_images=None,
            sort_by="updated_at",
            sort_dir="desc",
            page=1,
            per_page=2,
            db=db,
        )

        assert response["status"] == "ok"
        payload = response["data"]
        assert "items" in payload
        assert "pagination" in payload
        assert payload["pagination"]["per_page"] == 2
        assert isinstance(payload["items"], list)

        if payload["items"]:
            vin = payload["items"][0]["vin"]
            detail = get_inventory_vehicle(vin=vin, db=db)
            assert detail["status"] == "ok"
            assert detail["data"]["vin"] == vin
            assert "display_images" in detail["data"]
            assert "hero_image" in detail["data"]
            assert "display_mode" in detail["data"]
            assert "inspection_status" in detail["data"]
