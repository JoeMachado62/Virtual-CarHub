"""Tests for VSS-based styleId resolution in the ChromeData service layer."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from app.services.chromedata_service import _best_vss_style, _resolve_style_via_vss


def _vehicle(**kwargs) -> SimpleNamespace:
    defaults = {
        "vin": "1FTFW1E80MFA00001",
        "year": 2024,
        "make": "Ford",
        "model": "F-150",
        "trim": None,
        "body_type": None,
        "sub_body_type": None,
        "drivetrain": None,
        "listing_id": None,
        "features_normalized": {},
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# _best_vss_style
# ---------------------------------------------------------------------------


class TestBestVssStyle:
    def test_exact_trim_match(self) -> None:
        styles = [
            {"styleId": 100, "trimName": "XL", "bodyType": "Regular Cab"},
            {"styleId": 200, "trimName": "XLT", "bodyType": "SuperCrew"},
            {"styleId": 300, "trimName": "Lariat", "bodyType": "SuperCrew"},
        ]
        vehicle = _vehicle(trim="XLT")
        result = _best_vss_style(styles, vehicle)
        assert result is not None
        assert result["styleId"] == 200

    def test_partial_trim_match_vehicle_subset(self) -> None:
        styles = [
            {"styleId": 100, "trimName": "XL Regular Cab 4WD", "bodyType": "Regular Cab"},
            {"styleId": 200, "trimName": "Lariat SuperCrew 4WD", "bodyType": "SuperCrew"},
            {"styleId": 300, "trimName": "XLT SuperCab", "bodyType": "SuperCab"},
        ]
        vehicle = _vehicle(trim="Lariat 4WD")
        result = _best_vss_style(styles, vehicle)
        assert result is not None
        assert result["styleId"] == 200

    def test_body_type_tiebreak(self) -> None:
        styles = [
            {"styleId": 100, "trim": "Base", "bodyType": "Regular Cab"},
            {"styleId": 200, "trim": "Base", "bodyType": "SuperCrew"},
        ]
        vehicle = _vehicle(trim="Base", body_type="SuperCrew")
        result = _best_vss_style(styles, vehicle)
        assert result is not None
        assert result["styleId"] == 200

    def test_fallback_to_first_style_with_id(self) -> None:
        styles = [
            {"styleId": 100, "trimName": "XL", "bodyType": "Regular Cab"},
            {"styleId": 200, "trimName": "XLT", "bodyType": "SuperCrew"},
        ]
        vehicle = _vehicle(trim=None, body_type=None)
        result = _best_vss_style(styles, vehicle)
        assert result is not None
        assert result["styleId"] == 100

    def test_skips_entries_without_style_id(self) -> None:
        styles = [
            {"trimName": "XLT", "bodyType": "SuperCrew"},
            {"styleId": 300, "trimName": "Lariat", "bodyType": "SuperCrew"},
        ]
        vehicle = _vehicle(trim="XLT")
        result = _best_vss_style(styles, vehicle)
        assert result is not None
        assert result["styleId"] == 300

    def test_empty_styles_returns_none(self) -> None:
        assert _best_vss_style([], _vehicle()) is None

    def test_no_valid_style_ids_returns_none(self) -> None:
        styles = [{"trimName": "XLT"}, {"trimName": "Lariat"}]
        assert _best_vss_style(styles, _vehicle(trim="XLT")) is None

    def test_style_description_used_as_fallback_trim(self) -> None:
        styles = [
            {"styleId": 100, "styleDescription": "F-150 XLT SuperCrew 4WD"},
            {"styleId": 200, "styleDescription": "F-150 Lariat SuperCrew 4WD"},
        ]
        vehicle = _vehicle(trim="Lariat")
        result = _best_vss_style(styles, vehicle)
        assert result is not None
        assert result["styleId"] == 200


# ---------------------------------------------------------------------------
# _resolve_style_via_vss
# ---------------------------------------------------------------------------


def _clear_vss_caches():
    import app.services.chromedata_service as svc
    svc._vss_make_cache.clear()
    svc._vss_model_cache.clear()


def _fake_vss_client(makes=None, models=None, styles=None):
    class FakeVssClient:
        def get_makes(self, **kwargs) -> dict[str, Any]:
            return makes or {"makes": []}

        def get_models(self, **kwargs) -> dict[str, Any]:
            return models or {"models": []}

        def get_styles(self, **kwargs) -> dict[str, Any]:
            return styles or {"styles": []}

    return FakeVssClient()


class TestResolveStyleViaVss:
    def test_returns_style_from_vss_response(self, monkeypatch) -> None:
        client = _fake_vss_client(
            makes={"makes": [{"makeCode": "FO", "make": "Ford"}]},
            models={"models": [{"model": "F-150"}]},
            styles={"styles": [
                {"styleId": 403565, "trimName": "Limited", "bodyType": "SuperCrew Cab Styleside"},
                {"styleId": 403570, "trimName": "XLT", "bodyType": "SuperCab Styleside"},
            ]},
        )
        monkeypatch.setattr("app.services.chromedata_service._get_vss_client", lambda: client)
        monkeypatch.setattr(
            "app.services.chromedata_service.settings",
            SimpleNamespace(chromedata_locale="en_US", has_chromedata_vss=True),
        )
        _clear_vss_caches()

        vehicle = _vehicle(trim="Limited", body_type="SuperCrew Cab Styleside")
        style_id, body_type, description = _resolve_style_via_vss(vehicle)

        assert style_id == 403565
        assert body_type == "SuperCrew Cab Styleside"
        assert description == "Limited"

    def test_returns_none_when_no_styles(self, monkeypatch) -> None:
        client = _fake_vss_client(
            makes={"makes": [{"makeCode": "FO", "make": "Ford"}]},
            models={"models": [{"model": "F-150"}]},
            styles={"styles": []},
        )
        monkeypatch.setattr("app.services.chromedata_service._get_vss_client", lambda: client)
        monkeypatch.setattr(
            "app.services.chromedata_service.settings",
            SimpleNamespace(chromedata_locale="en_US", has_chromedata_vss=True),
        )
        _clear_vss_caches()

        vehicle = _vehicle()
        style_id, body_type, description = _resolve_style_via_vss(vehicle)
        assert style_id is None

    def test_returns_none_when_make_not_found(self, monkeypatch) -> None:
        client = _fake_vss_client(
            makes={"makes": [{"makeCode": "CH", "make": "Chevrolet"}]},
        )
        monkeypatch.setattr("app.services.chromedata_service._get_vss_client", lambda: client)
        monkeypatch.setattr(
            "app.services.chromedata_service.settings",
            SimpleNamespace(chromedata_locale="en_US", has_chromedata_vss=True),
        )
        _clear_vss_caches()

        vehicle = _vehicle(make="Ford")
        style_id, body_type, description = _resolve_style_via_vss(vehicle)
        assert style_id is None

    def test_returns_none_when_model_not_found(self, monkeypatch) -> None:
        client = _fake_vss_client(
            makes={"makes": [{"makeCode": "FO", "make": "Ford"}]},
            models={"models": [{"model": "Mustang"}]},
        )
        monkeypatch.setattr("app.services.chromedata_service._get_vss_client", lambda: client)
        monkeypatch.setattr(
            "app.services.chromedata_service.settings",
            SimpleNamespace(chromedata_locale="en_US", has_chromedata_vss=True),
        )
        _clear_vss_caches()

        vehicle = _vehicle(model="F-150")
        style_id, body_type, description = _resolve_style_via_vss(vehicle)
        assert style_id is None

    def test_resolves_model_with_different_casing(self, monkeypatch) -> None:
        client = _fake_vss_client(
            makes={"makes": [{"makeCode": "MA", "make": "Mazda"}]},
            models={"models": [{"model": "Mazda3"}]},
            styles={"styles": [{"styleId": 500, "trimName": "Sport", "bodyType": "Hatchback"}]},
        )
        monkeypatch.setattr("app.services.chromedata_service._get_vss_client", lambda: client)
        monkeypatch.setattr(
            "app.services.chromedata_service.settings",
            SimpleNamespace(chromedata_locale="en_US", has_chromedata_vss=True),
        )
        _clear_vss_caches()

        vehicle = _vehicle(make="Mazda", model="MAZDA3", trim="Sport", body_type="Hatchback")
        style_id, body_type, description = _resolve_style_via_vss(vehicle)
        assert style_id == 500
