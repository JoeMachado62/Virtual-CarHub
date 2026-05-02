from datetime import UTC, datetime

from sqlalchemy import delete, select

from app.api.v1 import routers as api_routers
from app.api.v1.routers.inventory import (
    _build_marketcheck_search_params,
    get_inventory_vehicle,
    inventory_facets,
    search_inventory,
)
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.models.entities import Vehicle, VehicleTaxonomyCache
from app.services.inventory_taxonomy_service import sync_marketcheck_taxonomy_cache
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



class StubMarketCheckTaxonomyClient:
    def __init__(self) -> None:
        self.live = True

    def get_terms(self, field: str, params: dict | None = None) -> dict:
        params = params or {}
        year = int(params.get("year", 0) or 0)
        make = params.get("make")
        model = params.get("model")

        if field == "make":
            if year == 2024:
                return {"terms": ["Honda", "Toyota"]}
            if year == 2025:
                return {"terms": ["Honda"]}
            return {"terms": []}

        if field == "model":
            if year == 2024 and make == "Honda":
                return {"terms": ["Civic", "Accord"]}
            if year == 2024 and make == "Toyota":
                return {"terms": ["Camry"]}
            if year == 2025 and make == "Honda":
                return {"terms": ["Civic"]}
            return {"terms": []}

        if field == "trim":
            if year == 2024 and make == "Honda" and model == "Civic":
                return {"terms": ["EX", "Sport"]}
            if year == 2024 and make == "Honda" and model == "Accord":
                return {"terms": ["Touring"]}
            if year == 2024 and make == "Toyota" and model == "Camry":
                return {"terms": ["SE"]}
            if year == 2025 and make == "Honda" and model == "Civic":
                return {"terms": ["Sport Touring"]}
            return {"terms": []}

        return {"terms": []}


class FailingMarketCheckClient:
    def __init__(self) -> None:
        self.live = True

    def search_inventory(self, params: dict) -> dict:
        _ = params
        raise RuntimeError(
            "Client error '422 unknown' for url "
            "'https://api.marketcheck.com/v2/search/car/active?rows=72&start=0&zip=33991&radius=250"
            "&dom_range=60-9999&api_key=super-secret-key'"
        )


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
            trim=None,
            body_type="SUV",
            source_type=None,
            state=None,
            exterior_color=None,
            interior_color=None,
            drivetrain=None,
            fuel_type=None,
            transmission=None,
            inventory_type=None,
            certified=None,
            single_owner=None,
            clean_title=None,
            min_dom=None,
            max_dom=None,
            min_price=None,
            max_price=None,
            min_year=None,
            max_year=None,
            min_miles=None,
            max_miles=None,
            has_images=None,
            sort_by="updated_at",
            sort_dir="desc",
            live_sync=False,
            sync_limit=72,
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


def test_search_auction_source_and_pricing_are_public_facing() -> None:
    init_db()
    vin = "1GNEK13ZX3R298984"
    listing_id = "ove-test-1GNEK13ZX3R298984"
    with SessionLocal() as db:
        db.execute(delete(Vehicle).where(Vehicle.vin == vin))
        db.execute(delete(Vehicle).where(Vehicle.listing_id == listing_id))
        db.add(
            Vehicle(
                vin=vin,
                listing_id=listing_id,
                year=2022,
                make="Cadillac",
                model="Escalade",
                trim="Premium Luxury",
                body_type="SUV",
                drivetrain="AWD",
                odometer=15420,
                price_asking=50000,
                location_zip="33312",
                location_state="FL",
                source_type="ove",
                source_url="https://example.com/source",
                features_normalized={
                    "transmission": "Automatic",
                    "exterior_color": "Black",
                    "interior_color": "Tan",
                    "auction_house": "Manheim Fort Lauderdale",
                    "pickup_location": "FL - FORT LAUDERDALE",
                    "status": "Live",
                    "inventory": "Buy Now",
                },
                available=True,
                quality_firewall_pass=True,
            )
        )
        db.commit()

        response = search_inventory(
            q=None,
            make="Cadillac",
            model=None,
            trim=None,
            body_type=None,
            source_type="auction",
            state=None,
            exterior_color=None,
            interior_color=None,
            drivetrain=None,
            fuel_type=None,
            transmission=None,
            inventory_type=None,
            certified=None,
            single_owner=None,
            clean_title=None,
            min_dom=None,
            max_dom=None,
            min_price=53249,
            max_price=53249,
            min_year=None,
            max_year=None,
            min_miles=None,
            max_miles=None,
            zip_code=None,
            radius=None,
            has_images=None,
            sort_by="price_asking",
            sort_dir="asc",
            live_sync=False,
            sync_limit=72,
            page=1,
            per_page=10,
            db=db,
        )

        assert response["status"] == "ok"
        items = response["data"]["items"]
        assert len(items) == 1
        item = items[0]
        assert item["source_filter_value"] == "auction"
        assert item["source_label"] == "Wholesale Direct"
        assert item["source_category"] == "auction"
        assert item["price_asking"] == 53249.0
        assert item["source_price"] == 50000.0
        assert item["buy_fee"] == 1000.0
        assert item["margin"] == 1500.0
        assert item["pricing"]["detail_shop_fee"] == 150.0
        assert item["pricing"]["marketing_fee"] == 599.0

        detail = get_inventory_vehicle(identifier=vin, db=db, current_user=None)
        assert detail["status"] == "ok"
        assert detail["data"]["price_asking"] == 53249.0
        assert detail["data"]["source_label"] == "Wholesale Direct"
        assert detail["data"]["pickup_location"] == "FL - FORT LAUDERDALE"


def test_search_wholesale_source_is_public_facing() -> None:
    init_db()
    wholesale_vins = ["2C3CDXCT5NH100001", "2C3CDXCT5NH100002", "2C3CDXCT5NH100003"]
    with SessionLocal() as db:
        db.execute(delete(Vehicle).where(Vehicle.vin.in_(wholesale_vins)))
        db.add_all(
            [
                Vehicle(
                    vin="2C3CDXCT5NH100001",
                    listing_id="marketcheck-wholesale-1",
                    year=2022,
                    make="Dodge",
                    model="Charger",
                    price_asking=31000,
                    source_type="marketcheck",
                    available=True,
                    quality_firewall_pass=True,
                    features_normalized={"days_on_market": 45},
                ),
                Vehicle(
                    vin="2C3CDXCT5NH100002",
                    listing_id="dealer-wholesale-1",
                    year=2022,
                    make="Dodge",
                    model="Challenger",
                    price_asking=32000,
                    source_type="dealer_wholesale",
                    available=True,
                    quality_firewall_pass=True,
                    features_normalized={"days_on_market": 55},
                ),
                Vehicle(
                    vin="2C3CDXCT5NH100003",
                    listing_id="dealer-partner-1",
                    year=2022,
                    make="Dodge",
                    model="Durango",
                    price_asking=33000,
                    source_type="dealer_partner",
                    available=True,
                    quality_firewall_pass=True,
                    features_normalized={"days_on_market": 75},
                ),
            ]
        )
        db.commit()

        response = search_inventory(
            q=None,
            make="Dodge",
            model=None,
            trim=None,
            body_type=None,
            source_type="wholesale",
            state=None,
            exterior_color=None,
            interior_color=None,
            drivetrain=None,
            fuel_type=None,
            transmission=None,
            inventory_type=None,
            certified=None,
            single_owner=None,
            clean_title=None,
            min_dom=None,
            max_dom=None,
            min_price=None,
            max_price=None,
            min_year=None,
            max_year=None,
            min_miles=None,
            max_miles=None,
            zip_code=None,
            radius=None,
            has_images=None,
            sort_by="updated_at",
            sort_dir="desc",
            live_sync=False,
            sync_limit=72,
            page=1,
            per_page=10,
            db=db,
        )

        assert response["status"] == "ok"
        items = response["data"]["items"]
        assert {item["vin"] for item in items} == {"2C3CDXCT5NH100001", "2C3CDXCT5NH100002"}
        assert all(item["source_filter_value"] == "wholesale" for item in items)
        assert all(item["source_label"] == "Wholesale" for item in items)

        detail = get_inventory_vehicle(vin="2C3CDXCT5NH100002", db=db)
        assert detail["status"] == "ok"
        assert detail["data"]["source_label"] == "Wholesale"


def test_search_enforces_aged_inventory_for_retail_but_bypasses_auction_dom() -> None:
    init_db()
    with SessionLocal() as db:
        for vin in ["1M8GDM9AXKP042788", "1M8GDM9AXKP042789", "1M8GDM9AXKP042780"]:
            db.execute(delete(Vehicle).where(Vehicle.vin == vin))
        db.commit()

        db.add_all(
            [
                Vehicle(
                    vin="1M8GDM9AXKP042788",
                    listing_id="retail-fresh-1",
                    year=2021,
                    make="BMW",
                    model="X5",
                    price_asking=30000,
                    source_type="marketcheck",
                    available=True,
                    features_normalized={"days_on_market": 12},
                ),
                Vehicle(
                    vin="1M8GDM9AXKP042789",
                    listing_id="retail-aged-1",
                    year=2021,
                    make="BMW",
                    model="X7",
                    price_asking=32000,
                    source_type="marketcheck",
                    available=True,
                    features_normalized={"days_on_market": 65},
                ),
                Vehicle(
                    vin="1M8GDM9AXKP042780",
                    listing_id="auction-fresh-1",
                    year=2021,
                    make="BMW",
                    model="XM",
                    price_asking=28000,
                    source_type="ove",
                    available=True,
                    features_normalized={"days_on_market": 5, "source_platform": "manheim"},
                ),
            ]
        )
        db.commit()

        response = search_inventory(
            q=None,
            make="BMW",
            model=None,
            trim=None,
            body_type=None,
            inventory_type=None,
            certified=None,
            source_type=None,
            state=None,
            exterior_color=None,
            interior_color=None,
            drivetrain=None,
            fuel_type=None,
            transmission=None,
            single_owner=None,
            clean_title=None,
            min_dom=None,
            max_dom=None,
            min_price=None,
            max_price=None,
            min_year=None,
            max_year=None,
            min_miles=None,
            max_miles=None,
            zip_code=None,
            radius=None,
            has_images=None,
            sort_by="updated_at",
            sort_dir="desc",
            live_sync=False,
            sync_limit=72,
            page=1,
            per_page=20,
            db=db,
        )

        vins = {item["vin"] for item in response["data"]["items"]}
        assert "1M8GDM9AXKP042788" not in vins
        assert "1M8GDM9AXKP042789" in vins
        assert "1M8GDM9AXKP042780" in vins


def test_search_applies_zip_radius_to_auction_inventory() -> None:
    init_db()
    near_vin = "2T1BURHE0JC074111"
    far_vin = "2T1BURHE0JC074112"
    with SessionLocal() as db:
        for vin in [near_vin, far_vin]:
            db.execute(delete(Vehicle).where(Vehicle.vin == vin))
        db.commit()

        db.add_all(
            [
                Vehicle(
                    vin=near_vin,
                    listing_id="ove-near-1",
                    year=2022,
                    make="Toyota",
                    model="Camry",
                    price_asking=28000,
                    location_zip="33312",
                    location_state="FL",
                    source_type="ove",
                    available=True,
                    quality_firewall_pass=True,
                ),
                Vehicle(
                    vin=far_vin,
                    listing_id="ove-far-1",
                    year=2022,
                    make="Toyota",
                    model="Camry",
                    price_asking=28000,
                    location_zip="90210",
                    location_state="CA",
                    source_type="ove",
                    available=True,
                    quality_firewall_pass=True,
                ),
            ]
        )
        db.commit()

        response = search_inventory(
            q=None,
            make="Toyota",
            model=None,
            trim=None,
            body_type=None,
            inventory_type=None,
            certified=None,
            source_type="auction",
            state=None,
            exterior_color=None,
            interior_color=None,
            drivetrain=None,
            fuel_type=None,
            transmission=None,
            single_owner=None,
            clean_title=None,
            min_dom=None,
            max_dom=None,
            min_price=None,
            max_price=None,
            min_year=None,
            max_year=None,
            min_miles=None,
            max_miles=None,
            zip_code="33312",
            radius=50,
            has_images=None,
            sort_by="updated_at",
            sort_dir="desc",
            live_sync=False,
            sync_limit=72,
            page=1,
            per_page=25,
            db=db,
        )

        assert response["status"] == "ok"
        vins = {item["vin"] for item in response["data"]["items"]}
    assert near_vin in vins
    assert far_vin not in vins


def test_search_infers_body_type_for_thin_auction_inventory() -> None:
    init_db()
    suv_vin = "5UX33EU01R9S49894"
    sedan_vin = "WBA53FJ03RCP81233"
    with SessionLocal() as db:
        db.execute(delete(Vehicle).where(Vehicle.vin.in_([suv_vin, sedan_vin])))
        db.add_all(
            [
                Vehicle(
                    vin=suv_vin,
                    listing_id="ove-thin-x5",
                    year=2024,
                    make="BMW",
                    model="X5",
                    body_type=None,
                    odometer=12000,
                    price_asking=55000,
                    location_zip="33312",
                    location_state="FL",
                    source_type="ove",
                    available=True,
                    quality_firewall_pass=True,
                ),
                Vehicle(
                    vin=sedan_vin,
                    listing_id="ove-thin-5-series",
                    year=2024,
                    make="BMW",
                    model="5 Series",
                    body_type=None,
                    odometer=12000,
                    price_asking=55000,
                    location_zip="33312",
                    location_state="FL",
                    source_type="ove",
                    available=True,
                    quality_firewall_pass=True,
                ),
            ]
        )
        db.commit()

        response = search_inventory(
            q=None,
            make="BMW",
            model=None,
            trim=None,
            body_type="SUV",
            inventory_type=None,
            certified=None,
            source_type="auction",
            state=None,
            exterior_color=None,
            interior_color=None,
            drivetrain=None,
            fuel_type=None,
            transmission=None,
            single_owner=None,
            clean_title=None,
            min_dom=None,
            max_dom=None,
            min_price=None,
            max_price=None,
            min_year=2024,
            max_year=2024,
            min_miles=None,
            max_miles=None,
            zip_code="33312",
            radius=50,
            has_images=None,
            sort_by="updated_at",
            sort_dir="desc",
            live_sync=False,
            sync_limit=72,
            page=1,
            per_page=25,
            db=db,
        )

    assert response["status"] == "ok"
    vins = {item["vin"] for item in response["data"]["items"]}
    assert suv_vin in vins
    assert sedan_vin not in vins


def test_inventory_taxonomy_cache_sync_and_facets() -> None:
    init_db()
    client = StubMarketCheckTaxonomyClient()
    taxonomy_vins = ["TAXONOMY-CIVIC-EX", "TAXONOMY-CIVIC-ST"]

    with SessionLocal() as db:
        db.execute(delete(VehicleTaxonomyCache))
        db.execute(delete(Vehicle).where(Vehicle.vin.in_(taxonomy_vins)))
        db.add_all(
            [
                Vehicle(
                    vin=taxonomy_vins[0],
                    year=2024,
                    make="Honda",
                    model="Civic",
                    trim="EX",
                    body_type="Sedan",
                    price_asking=24500,
                    available=True,
                ),
                Vehicle(
                    vin=taxonomy_vins[1],
                    year=2025,
                    make="Honda",
                    model="Civic",
                    trim="Sport Touring",
                    body_type="Hatchback",
                    price_asking=31500,
                    available=True,
                ),
            ]
        )
        db.commit()

        report = sync_marketcheck_taxonomy_cache(db, client=client, start_year=2024, end_year=2025)
        db.commit()

        assert report.inserted == 5
        assert report.deleted == 0
        civic_ex = db.scalar(
            select(VehicleTaxonomyCache).where(
                VehicleTaxonomyCache.year == 2024,
                VehicleTaxonomyCache.make == "Honda",
                VehicleTaxonomyCache.model == "Civic",
                VehicleTaxonomyCache.trim == "EX",
            )
        )
        civic_sport_touring = db.scalar(
            select(VehicleTaxonomyCache).where(
                VehicleTaxonomyCache.year == 2025,
                VehicleTaxonomyCache.make == "Honda",
                VehicleTaxonomyCache.model == "Civic",
                VehicleTaxonomyCache.trim == "Sport Touring",
            )
        )
        assert civic_ex is not None
        assert civic_ex.body_type == "Sedan"
        assert civic_sport_touring is not None
        assert civic_sport_touring.body_type == "Hatchback"

        response = inventory_facets(
            q=None,
            make="Honda",
            model="Civic",
            trim=None,
            body_type=None,
            state=None,
            inventory_type=None,
            source_type=None,
            exterior_color=None,
            interior_color=None,
            min_price=None,
            max_price=None,
            min_year=2024,
            max_year=2025,
            min_miles=None,
            max_miles=None,
            has_images=False,
            use_marketcheck=False,
            db=db,
        )

    assert response["status"] == "ok"
    taxonomy = response["data"]["taxonomy"]
    assert taxonomy["source"] == "taxonomy_cache"
    assert [bucket["item"] for bucket in taxonomy["years"]] == ["2025", "2024"]
    assert [bucket["item"] for bucket in taxonomy["make"]] == ["Honda", "Toyota"]
    assert [bucket["item"] for bucket in taxonomy["model"]] == ["Accord", "Civic"]
    assert [bucket["item"] for bucket in taxonomy["trim"]] == ["EX", "Sport", "Sport Touring"]
    lookup = taxonomy["lookup"]
    assert lookup["body_types_by_make_model"]["Honda|||Civic"] == ["Hatchback", "Sedan"]
    assert lookup["body_types_by_make_model_trim"]["Honda|||Civic|||EX"] == ["Sedan"]


def test_build_marketcheck_search_params_includes_dom_range() -> None:
    params = _build_marketcheck_search_params(
        q=None,
        make=None,
        model=None,
        trim=None,
        body_type=None,
        state=None,
        min_price=None,
        max_price=None,
        min_year=None,
        max_year=None,
        has_images=None,
        exterior_color=None,
        interior_color=None,
        drivetrain=None,
        fuel_type=None,
        transmission=None,
        inventory_type=None,
        certified=None,
        single_owner=None,
        clean_title=None,
        min_dom=60,
        max_dom=120,
        zip_code="33991",
        radius=250,
    )

    assert params["zip"] == "33991"
    assert params["radius"] == 250
    assert params["dom_range"] == "60-120"


def test_search_live_sync_falls_back_without_leaking_vendor_error(monkeypatch) -> None:
    init_db()
    with SessionLocal() as db:
        monkeypatch.setattr(api_routers.inventory, "_marketcheck_client", lambda: FailingMarketCheckClient())
        monkeypatch.setattr(api_routers.inventory.settings, "marketcheck_api_key", "test-key")

        response = search_inventory(
            q=None,
            make=None,
            model=None,
            trim=None,
            body_type=None,
            inventory_type=None,
            certified=None,
            source_type=None,
            state=None,
            exterior_color=None,
            interior_color=None,
            drivetrain=None,
            fuel_type=None,
            transmission=None,
            single_owner=None,
            clean_title=None,
            min_dom=None,
            max_dom=None,
            min_price=None,
            max_price=None,
            min_year=None,
            max_year=None,
            min_miles=None,
            max_miles=None,
            zip_code="33991",
            radius=250,
            has_images=None,
            sort_by="updated_at",
            sort_dir="desc",
            live_sync=True,
            sync_limit=72,
            page=1,
            per_page=18,
            db=db,
        )

    assert response["status"] == "ok"
    sync = response["data"]["sync"]
    assert sync["mode"] == "fallback"
    assert sync["error"] == "Live wholesale sync is temporarily unavailable. Showing saved inventory results."
    assert "api_key" not in sync["error"]
    assert "marketcheck.com" not in sync["error"]
