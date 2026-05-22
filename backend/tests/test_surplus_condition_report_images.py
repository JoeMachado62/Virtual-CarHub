from app.api.v1.routers.me import _surplus_marketcheck_storage_key


def test_surplus_marketcheck_storage_key_is_stable_and_vin_scoped() -> None:
    key = _surplus_marketcheck_storage_key(
        vin="WDDUG8GBXFA123456",
        source_url="https://images.example.com/cars/photo.jpeg?token=secret&w=800",
        display_order=7,
    )

    assert key.startswith("source-cache/WDDUG8GBXFA123456/marketcheck/007-")
    assert key.endswith(".jpg")
    assert "token" not in key
