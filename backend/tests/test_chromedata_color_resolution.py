from __future__ import annotations

from types import SimpleNamespace

from app.services.chromedata_service import (
    CHROMEDATA_COLOR_PIPELINE_VERSION,
    _normalize_items,
    _parse_cvd_descriptor,
    _parse_media_response,
    chromedata_assets_need_refresh,
)


def _vehicle(**kwargs):
    defaults = {
        "vin": "1FAHP2E80DG100001",
        "year": 2020,
        "make": "Ford",
        "model": "Test",
        "trim": "SEL",
        "body_type": "Sedan",
        "sub_body_type": None,
        "exterior_color": None,
        "features_normalized": {},
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_normalize_items_keeps_single_color_object_with_styles_list() -> None:
    color = {
        "genericDesc": "Black",
        "description": "Agate Black Metallic",
        "colorCode": "UM",
        "styles": ["401234"],
        "type": 1,
    }

    assert _normalize_items(color) == [color]


def test_cvd_color_resolution_prefers_listing_color_match_over_conflicting_installed_color() -> None:
    vehicle = _vehicle(features_normalized={"exterior_color": "Black"})
    response = {
        "result": {
            "vehicles": [{"styleId": 401234, "styleDescription": "SEL AWD", "bodyType": "Sedan"}],
            "exteriorColors": [
                {
                    "genericDesc": "Blue",
                    "description": "Velocity Blue Metallic",
                    "colorCode": "E7",
                    "installCause": "E",
                    "styles": ["401234"],
                    "type": 1,
                    "primary": True,
                },
                {
                    "genericDesc": "Black",
                    "description": "Agate Black Metallic",
                    "colorCode": "UM",
                    "styles": ["401234"],
                    "type": 1,
                    "primary": True,
                },
            ],
        }
    }

    descriptor = _parse_cvd_descriptor(response, vehicle)

    assert descriptor["color_code"] == "UM"
    assert descriptor["color_info"].match_source == "listing_text"
    assert descriptor["color_info"].is_exact_match is True


def test_cvd_color_resolution_uses_neutral_fallback_when_listing_color_is_unavailable() -> None:
    vehicle = _vehicle(features_normalized={"exterior_color": "Green"})
    response = {
        "result": {
            "vehicles": [{"styleId": 401234, "styleDescription": "SEL AWD", "bodyType": "Sedan"}],
            "exteriorColors": [
                {
                    "genericDesc": "Blue",
                    "description": "Velocity Blue Metallic",
                    "colorCode": "E7",
                    "installCause": "E",
                    "styles": ["401234"],
                    "type": 1,
                    "primary": True,
                },
                {
                    "genericDesc": "Black",
                    "description": "Agate Black Metallic",
                    "colorCode": "UM",
                    "styles": ["401234"],
                    "type": 1,
                    "primary": True,
                },
            ],
        }
    }

    descriptor = _parse_cvd_descriptor(response, vehicle)

    assert descriptor["color_code"] == ""
    assert descriptor["color_info"] is None
    assert descriptor["color_match_fallback_reason"] == "listing_generic_color_unavailable"


def test_cvd_color_resolution_matches_generic_color_aliases() -> None:
    vehicle = _vehicle(features_normalized={"exterior_color": "Charcoal"})
    response = {
        "result": {
            "vehicles": [{"styleId": 401234, "styleDescription": "SEL AWD", "bodyType": "Sedan"}],
            "exteriorColors": [
                {
                    "genericDesc": "Gray",
                    "description": "Carbonized Gray Metallic",
                    "colorCode": "M7",
                    "styles": ["401234"],
                    "type": 1,
                    "primary": True,
                },
                {
                    "genericDesc": "Blue",
                    "description": "Velocity Blue Metallic",
                    "colorCode": "E7",
                    "styles": ["401234"],
                    "type": 1,
                    "primary": True,
                },
            ],
        }
    }

    descriptor = _parse_cvd_descriptor(response, vehicle)

    assert descriptor["color_code"] == "M7"
    assert descriptor["color_info"].generic_desc == "Gray"


def test_media_response_uses_matching_primary_color_option_code() -> None:
    response = {
        "styleMedia": {
            "colorized": [
                {
                    "@primaryColorOptionCode": "E7",
                    "@width": "640",
                    "@shotCode": "01",
                    "@backgroundDescription": "Transparent",
                    "@href": "https://media.example/blue_01.png",
                },
                {
                    "@primaryColorOptionCode": "UM",
                    "@width": "640",
                    "@shotCode": "01",
                    "@backgroundDescription": "Transparent",
                    "@href": "https://media.example/black_01.png",
                },
                {
                    "@primaryColorOptionCode": "UM",
                    "@width": "640",
                    "@shotCode": "02",
                    "@backgroundDescription": "Transparent",
                    "@href": "https://media.example/black_02.png",
                },
            ],
            "view": [
                {
                    "@width": "640",
                    "@shotCode": "01",
                    "@backgroundDescription": "White",
                    "@href": "https://media.example/generic_01.jpg",
                }
            ],
        }
    }

    parsed = _parse_media_response(response, detail_level="card", selected_color_code="UM")

    assert parsed is not None
    assert parsed["gallery_urls"] == ["https://media.example/black_01.png", "https://media.example/black_02.png"]


def test_media_response_prefers_matching_secondary_color_option_code_for_two_tone() -> None:
    response = {
        "styleMedia": {
            "colorized": [
                {
                    "@primaryColorOptionCode": "UM",
                    "@secondaryColorOptionCode": "YZ",
                    "@width": "640",
                    "@shotCode": "01",
                    "@backgroundDescription": "Transparent",
                    "@href": "https://media.example/black_white_01.png",
                },
                {
                    "@primaryColorOptionCode": "UM",
                    "@secondaryColorOptionCode": "CN",
                    "@width": "640",
                    "@shotCode": "01",
                    "@backgroundDescription": "Transparent",
                    "@href": "https://media.example/black_red_01.png",
                },
            ],
        }
    }

    parsed = _parse_media_response(
        response,
        detail_level="card",
        selected_color_code="UM",
        selected_secondary_color_code="CN",
    )

    assert parsed is not None
    assert parsed["gallery_urls"] == ["https://media.example/black_red_01.png"]


def test_chromedata_assets_need_refresh_for_legacy_or_color_mismatched_assets() -> None:
    vehicle = _vehicle(features_normalized={"exterior_color": "Black"})
    legacy_asset = SimpleNamespace(
        active=True,
        role="hero",
        source_kind="chromedata",
        metadata_json={"color_code": "", "color_description": "", "color_match_exact": False},
    )
    current_asset = SimpleNamespace(
        active=True,
        role="hero",
        source_kind="chromedata",
        metadata_json={
            "color_pipeline_version": CHROMEDATA_COLOR_PIPELINE_VERSION,
            "color_code": "UM",
            "color_description": "Agate Black Metallic",
            "color_generic": "Black",
            "color_match_exact": True,
        },
    )

    assert chromedata_assets_need_refresh(vehicle, [legacy_asset]) is True
    assert chromedata_assets_need_refresh(vehicle, [current_asset]) is False
