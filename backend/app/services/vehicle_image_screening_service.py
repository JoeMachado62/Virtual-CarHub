from __future__ import annotations

import base64
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode, urlsplit, urlunsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.constants import ImageTier
from app.models.entities import VehicleImageAsset
from app.services.image_pipeline_service import canonical_source_image_url

logger = logging.getLogger(__name__)

GEMINI_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
SCREENING_CACHE_KEY = "overlay_screening"
SCREENING_VERSION = "2026-05-20-v1"
SCREENING_REJECT_CLASSIFICATIONS = {
    "has_text_overlay",
    "has_graphic_overlay",
    "has_ui_or_screenshot_elements",
    "not_vehicle_photo",
}
SCREENING_CROP_CLASSIFICATIONS = {
    "has_text_overlay",
    "has_graphic_overlay",
}
URL_REJECT_PATTERNS = re.compile(
    r"(logo|banner|badge|overlay|sprite|icon|placeholder|watermark|no[_-]?photo|coming[_-]?soon|map|avatar)",
    re.IGNORECASE,
)

SCREENING_PROMPT = """
You are reviewing vehicle listing photos for VirtualCarHub.

Determine whether this image is a clean base vehicle photo or whether it contains added marketing or graphic overlays.

Classify as exactly one of:
- clean_vehicle_photo
- has_text_overlay
- has_graphic_overlay
- has_ui_or_screenshot_elements
- not_vehicle_photo
- uncertain

Look for text, price labels, dealer logos, phone numbers, badges, banners, arrows, colored callouts,
watermarks, UI cards, app screenshots, borders, stickers, promotional graphics, collage layouts,
or other composite design elements.

If the overlay is confined mostly to a top or bottom band and the vehicle remains usable after cropping,
set "crop_recommendation" to one of: crop_top_10, crop_bottom_10, crop_vertical_10, crop_vertical_15.
If cropping would cut off the vehicle or the overlay is across the center of the image, use "none".

Return only valid JSON:
{
  "classification": "...",
  "has_overlay": true,
  "overlay_types": [],
  "visible_text": [],
  "crop_recommendation": "none",
  "confidence": 0.0,
  "reason": "brief explanation"
}
""".strip()


def screen_marketcheck_vehicle_images(
    db: Session,
    *,
    vin: str,
    image_urls: list[str],
    max_images: int | None = None,
) -> list[str]:
    """Return only image URLs approved by the overlay/branding screening pipeline.

    Gemini is the primary vision model. OpenAI vision is used as the fallback
    when Gemini is unavailable or returns an unusable answer. Results are
    cached in VehicleImageAsset.metadata_json so repeated modal opens do not
    re-bill model calls for already-screened photos.
    """
    if not settings.image_screening_enabled:
        return image_urls

    limit = max(1, int(max_images or settings.image_screening_max_images or 60))
    candidate_urls = image_urls[:limit]
    assets_by_key = _load_marketcheck_assets_by_key(db, vin)
    approved: list[str] = []

    for url in candidate_urls:
        key = canonical_source_image_url(url)
        asset = assets_by_key.get(key)
        cached = _cached_screening(asset)
        if cached:
            display_url = _display_url(url, cached)
            if cached.get("approved") is True and display_url:
                approved.append(display_url)
            continue

        result = _cheap_precheck(url)
        if result is None:
            result = _screen_with_models(url)

        if asset:
            metadata = dict(asset.metadata_json or {})
            metadata[SCREENING_CACHE_KEY] = result
            asset.metadata_json = metadata
            asset.active = bool(result.get("approved"))
        display_url = _display_url(url, result)
        if result.get("approved") is True and display_url:
            approved.append(display_url)

    return approved


def _load_marketcheck_assets_by_key(db: Session, vin: str) -> dict[str, VehicleImageAsset]:
    assets = db.scalars(
        select(VehicleImageAsset).where(
            VehicleImageAsset.vin == vin,
            VehicleImageAsset.tier == ImageTier.SOURCE_CACHE,
            VehicleImageAsset.source_kind == "marketcheck",
        )
    ).all()
    out: dict[str, VehicleImageAsset] = {}
    for asset in assets:
        key = canonical_source_image_url(asset.external_url or "")
        if key and key not in out:
            out[key] = asset
    return out


def _cached_screening(asset: VehicleImageAsset | None) -> dict[str, Any] | None:
    if not asset:
        return None
    screening = (asset.metadata_json or {}).get(SCREENING_CACHE_KEY)
    if not isinstance(screening, dict):
        return None
    if screening.get("version") != SCREENING_VERSION:
        return None
    if isinstance(screening.get("approved"), bool):
        return screening
    return None


def _cheap_precheck(url: str) -> dict[str, Any] | None:
    if URL_REJECT_PATTERNS.search(url):
        return _result(
            provider="precheck",
            model="url-pattern",
            classification="has_graphic_overlay",
            has_overlay=True,
            overlay_types=["url_marketing_keyword"],
            visible_text=[],
            crop_recommendation="none",
            confidence=0.7,
            reason="URL contains a common marketing/graphic asset keyword.",
        )
    return None


def _display_url(url: str, screening: dict[str, Any]) -> str | None:
    if screening.get("approved") is not True:
        return None
    crop = str(screening.get("crop_recommendation") or "none")
    if crop == "none":
        return url
    return _append_crop_fragment(url, crop)


def _append_crop_fragment(url: str, crop: str) -> str:
    parts = urlsplit(url)
    fragment = urlencode({"vch_crop": crop})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, fragment))


def _screen_with_models(url: str) -> dict[str, Any]:
    try:
        image_bytes, mime_type = _download_image(url)
    except Exception as exc:
        logger.info("image_screening_download_failed url=%s", url, exc_info=True)
        return _failure_result("download", str(exc))

    if settings.has_gemini:
        try:
            return _screen_with_gemini(image_bytes, mime_type)
        except Exception:
            logger.info("gemini_image_screening_failed url=%s", url, exc_info=True)

    if settings.has_openai:
        try:
            return _screen_with_openai(image_bytes, mime_type)
        except Exception:
            logger.info("openai_image_screening_failed url=%s", url, exc_info=True)

    return _failure_result("model_unavailable", "No image screening model returned a usable decision.")


def _download_image(url: str) -> tuple[bytes, str]:
    with httpx.Client(timeout=20.0, follow_redirects=True) as client:
        response = client.get(url)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if not content_type.startswith("image/"):
            content_type = "image/jpeg"
        return response.content, content_type


def _screen_with_gemini(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    payload = {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": mime_type,
                            "data": base64.b64encode(image_bytes).decode("ascii"),
                        }
                    },
                    {"text": SCREENING_PROMPT},
                ]
            }
        ],
        "generationConfig": {
            "response_mime_type": "application/json",
            "temperature": 0,
        },
    }
    url = GEMINI_GENERATE_URL.format(model=settings.gemini_image_screening_model)
    with httpx.Client(timeout=45.0) as client:
        response = client.post(
            url,
            headers={
                "x-goog-api-key": settings.gemini_api_key,
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    text = "".join(
        str(part.get("text") or "")
        for candidate in data.get("candidates", [])
        for part in ((candidate.get("content") or {}).get("parts") or [])
        if isinstance(part, dict)
    ).strip()
    parsed = _parse_json_object(text)
    return _normalize_model_result(parsed, provider="gemini", model=settings.gemini_image_screening_model)


def _screen_with_openai(image_bytes: bytes, mime_type: str) -> dict[str, Any]:
    data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    payload = {
        "model": settings.openai_image_screening_model,
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": SCREENING_PROMPT},
                    {"type": "input_image", "image_url": data_url, "detail": "high"},
                ],
            }
        ],
        "text": {"format": {"type": "json_object"}},
    }
    with httpx.Client(timeout=45.0) as client:
        response = client.post(
            OPENAI_RESPONSES_URL,
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        response.raise_for_status()
        data = response.json()
    chunks: list[str] = []
    if isinstance(data.get("output_text"), str):
        chunks.append(data["output_text"])
    for output in data.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                chunks.append(str(content.get("text") or ""))
    parsed = _parse_json_object("".join(chunks))
    return _normalize_model_result(parsed, provider="openai", model=settings.openai_image_screening_model)


def _parse_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise ValueError("image screening response was not a JSON object")
    return parsed


def _normalize_model_result(parsed: dict[str, Any], *, provider: str, model: str) -> dict[str, Any]:
    classification = str(parsed.get("classification") or "uncertain").strip()
    has_overlay = bool(parsed.get("has_overlay")) or classification in SCREENING_REJECT_CLASSIFICATIONS
    confidence = _coerce_confidence(parsed.get("confidence"))
    crop_recommendation = _normalize_crop_recommendation(parsed.get("crop_recommendation"))
    crop_salvage = (
        crop_recommendation != "none"
        and classification in SCREENING_CROP_CLASSIFICATIONS
        and confidence >= 0.65
    )
    approved = (classification == "clean_vehicle_photo" and not has_overlay and confidence >= 0.55) or crop_salvage
    return _result(
        provider=provider,
        model=model,
        classification=classification,
        has_overlay=has_overlay,
        overlay_types=_string_list(parsed.get("overlay_types")),
        visible_text=_string_list(parsed.get("visible_text")),
        crop_recommendation=crop_recommendation,
        confidence=confidence,
        reason=str(parsed.get("reason") or ""),
        approved=approved,
    )


def _result(
    *,
    provider: str,
    model: str,
    classification: str,
    has_overlay: bool,
    overlay_types: list[str],
    visible_text: list[str],
    crop_recommendation: str = "none",
    confidence: float,
    reason: str,
    approved: bool | None = None,
) -> dict[str, Any]:
    return {
        "version": SCREENING_VERSION,
        "provider": provider,
        "model": model,
        "classification": classification,
        "has_overlay": has_overlay,
        "overlay_types": overlay_types,
        "visible_text": visible_text,
        "crop_recommendation": crop_recommendation,
        "confidence": confidence,
        "reason": reason[:240],
        "approved": (not has_overlay and classification == "clean_vehicle_photo") if approved is None else approved,
        "screened_at": datetime.now(UTC).isoformat(),
    }


def _failure_result(provider: str, reason: str) -> dict[str, Any]:
    return _result(
        provider=provider,
        model="none",
        classification="uncertain",
        has_overlay=True,
        overlay_types=["screening_failed"],
        visible_text=[],
        crop_recommendation="none",
        confidence=0.0,
        reason=reason,
        approved=False,
    )


def _coerce_confidence(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, number))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:120] for item in value if str(item).strip()]


def _normalize_crop_recommendation(value: Any) -> str:
    text = str(value or "none").strip().lower()
    if text in {"crop_top_10", "crop_bottom_10", "crop_vertical_10", "crop_vertical_15"}:
        return text
    return "none"
