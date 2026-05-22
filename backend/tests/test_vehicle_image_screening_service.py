from app.services.vehicle_image_screening_service import (
    _cheap_precheck,
    _failure_result,
    _normalize_model_result,
)


def test_screening_allows_dashboard_navigation_text() -> None:
    result = _normalize_model_result(
        {
            "classification": "has_ui_or_screenshot_elements",
            "has_overlay": True,
            "overlay_types": ["infotainment display"],
            "visible_text": ["MapQuest", "Navigation"],
            "crop_recommendation": "none",
            "confidence": 0.93,
            "reason": "Map text appears on the vehicle dashboard screen.",
        },
        provider="test",
        model="test-model",
    )

    assert result["approved"] is True


def test_screening_allows_license_plate_frame_dealer_name() -> None:
    result = _normalize_model_result(
        {
            "classification": "has_text_overlay",
            "has_overlay": True,
            "overlay_types": ["small text"],
            "visible_text": ["Fort Myers Acura"],
            "crop_recommendation": "none",
            "confidence": 0.88,
            "reason": "Small dealer name is on the physical license plate frame.",
        },
        provider="test",
        model="test-model",
    )

    assert result["approved"] is True


def test_screening_allows_license_plate_frame_phone_or_website() -> None:
    result = _normalize_model_result(
        {
            "classification": "has_text_overlay",
            "has_overlay": True,
            "overlay_types": ["license plate frame text", "phone number"],
            "visible_text": ["HYUNDAI OF FORT MYERS", "239-555-1212", "dealer.com"],
            "crop_recommendation": "none",
            "confidence": 0.94,
            "reason": "Text appears on the physical vehicle license plate frame.",
        },
        provider="test",
        model="test-model",
    )

    assert result["approved"] is True


def test_screening_rejects_clear_marketing_overlay() -> None:
    result = _normalize_model_result(
        {
            "classification": "has_text_overlay",
            "has_overlay": True,
            "overlay_types": ["marketing banner", "phone number"],
            "visible_text": ["CALL 239-555-1212", "SPECIAL OFFER"],
            "crop_recommendation": "none",
            "confidence": 0.91,
            "reason": "Large promotional banner was added over the photo.",
        },
        provider="test",
        model="test-model",
    )

    assert result["approved"] is False


def test_screening_rejects_text_only_marketing_graphic_without_vehicle() -> None:
    result = _normalize_model_result(
        {
            "classification": "has_text_overlay",
            "has_overlay": True,
            "overlay_types": ["text_overlay", "marketing_graphic"],
            "visible_text": ["Buy with confidence", "30 day / 1,000 mile limited warranty"],
            "crop_recommendation": "none",
            "confidence": 0.95,
            "reason": "The image is a marketing graphic with promotional text, not a photograph of a vehicle.",
        },
        provider="test",
        model="test-model",
    )

    assert result["approved"] is False


def test_screening_allows_oem_badge_or_model_emblem() -> None:
    result = _normalize_model_result(
        {
            "classification": "has_graphic_overlay",
            "has_overlay": True,
            "overlay_types": ["badge", "logo"],
            "visible_text": ["GLS 450", "4MATIC"],
            "crop_recommendation": "none",
            "confidence": 0.96,
            "reason": "Visible model badge and manufacturer emblem attached to the vehicle.",
        },
        provider="test",
        model="test-model",
    )

    assert result["approved"] is True


def test_screening_allows_marketing_words_when_not_added_overlay() -> None:
    result = _normalize_model_result(
        {
            "classification": "has_text_overlay",
            "has_overlay": True,
            "overlay_types": ["visible text"],
            "visible_text": ["HYUNDAI OF FORT MYERS", "dealer.com"],
            "crop_recommendation": "none",
            "confidence": 0.95,
            "reason": "Dealer website text is visible on the original vehicle plate frame, not an added overlay.",
        },
        provider="test",
        model="test-model",
    )

    assert result["approved"] is True


def test_url_precheck_does_not_reject_map_photo_urls() -> None:
    assert _cheap_precheck("https://dealer.example/images/mapquest-dashboard-photo.jpg") is None


def test_url_precheck_does_not_reject_badge_photo_urls() -> None:
    assert _cheap_precheck("https://dealer.example/images/rear-model-badge-photo.jpg") is None


def test_screening_failures_do_not_hide_clean_photos() -> None:
    result = _failure_result("download", "temporary CDN timeout")

    assert result["approved"] is True
