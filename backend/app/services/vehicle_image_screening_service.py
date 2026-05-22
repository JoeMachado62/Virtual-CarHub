from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
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
from app.services.image_pipeline_service import _asset_url, canonical_source_image_url

logger = logging.getLogger(__name__)

GEMINI_GENERATE_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
SCREENING_CACHE_KEY = "overlay_screening"
SCREENING_VERSION = "2026-05-21-v6"
SCREENING_REJECT_CLASSIFICATIONS = {
    "has_text_overlay",
    "has_graphic_overlay",
    "not_vehicle_photo",
}
SCREENING_CROP_CLASSIFICATIONS = {
    "has_text_overlay",
    "has_graphic_overlay",
}
URL_REJECT_PATTERNS = re.compile(
    r"(banner|overlay|sprite|icon|placeholder|watermark|no[_-]?photo|coming[_-]?soon|avatar)",
    re.IGNORECASE,
)
MARKETING_SIGNAL_RE = re.compile(
    r"("
    r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b|"
    r"\bcall\b|\bsale\b|\bspecial\b|\boffer\b|\bfinanc(?:e|ing)\b|"
    r"\bpayment\b|\bdown\b|\bapr\b|\bwarranty\b|\bcertified\b|\bshop\b|"
    r"\bvisit\b|\bwww\.|\.com\b|@|#|"
    r"\$\s?\d|"
    r"\bwatermark\b|\bbanner\b"
    r")",
    re.IGNORECASE,
)
ADDED_OVERLAY_CONTEXT_RE = re.compile(
    r"("
    r"\badded\s+(?:text|graphic|banner|overlay|watermark|callout)\b|"
    r"\b(?:text|graphic|banner|watermark|callout)\s+(?:was\s+)?(?:added|overlaid|superimposed)\b|"
    r"\bplaced\s+on\s+top\b|\bsuperimposed\b|\boverlaid\b|"
    r"\bpromotional\s+(?:banner|graphic|image)\b|\bmarketing\s+(?:banner|graphic|image)\b|\bdealer\s+watermark\b|"
    r"\bprice\s+callout\b|\bpayment\s+callout\b|"
    r"\bdesign\s+elements?\b|\bcollage\b|\bcomposite\b|"
    r"\bapp\s+screenshot\b|\bui\s+screenshot\b"
    r")",
    re.IGNORECASE,
)
NEGATED_ADDED_OVERLAY_RE = re.compile(
    r"\b(?:no|not|without|lacks|does\s+not\s+contain)\b.{0,40}"
    r"\b(?:added|overlay|overlaid|superimposed|banner|watermark|callout|composite|screenshot)\b",
    re.IGNORECASE,
)
INCIDENTAL_TEXT_RE = re.compile(
    r"("
    r"\bmapquest\b|\bmap\b|\bgps\b|\bnavigation\b|\bnav\b|\bodometer\b|\bodo\b|"
    r"\bmiles?\b|\bmi\b|\bvin\b|\blicense\b|\bplate\b|\bfort\s+myers\s+acura\b|"
    r"\bacura\b|\bhonda\b|\btoyota\b|\bford\b|\bchevrolet\b|\bnissan\b|\bhyundai\b|"
    r"\bkia\b|\bmazda\b|\blexus\b|\bbmw\b|\bmercedes\b|\baudi\b|"
    r"\bbadge\b|\bemblem\b|\bmodel\b|\btrim\b"
    r")",
    re.IGNORECASE,
)
LICENSE_PLATE_CONTEXT_RE = re.compile(
    r"("
    r"\blicense\b|\bplate\b|\bplate\s+frame\b|\btag\b|\btemporary\s+tag\b|"
    r"\bdealer\s+plate\b|\bvehicle\s+plate\b"
    r")",
    re.IGNORECASE,
)
NON_VEHICLE_MARKETING_RE = re.compile(
    r"("
    r"\bnot\s+(?:a\s+)?(?:photo|photograph|image|picture)\s+of\s+(?:a\s+)?vehicle\b|"
    r"\bno\s+vehicle\b|\bwithout\s+(?:a\s+)?vehicle\b|"
    r"\bmarketing\s+(?:graphic|image|billboard|poster|flyer)\b|"
    r"\bpromotional\s+(?:graphic|image|billboard|poster|flyer)\b|"
    r"\btext[- ]only\s+(?:graphic|image|billboard|poster|flyer)\b"
    r")",
    re.IGNORECASE,
)

SCREENING_PROMPT = """
You are reviewing vehicle listing photos for VirtualCarHub.

Determine whether this image is a usable vehicle listing photo or whether it contains added marketing or graphic overlays that should be hidden from a public gallery.

Classify as exactly one of:
- clean_vehicle_photo
- has_text_overlay
- has_graphic_overlay
- has_ui_or_screenshot_elements
- not_vehicle_photo
- uncertain

Reject only clear added promotional/composite content: phone numbers, websites, social handles, price/payment
callouts, large dealer marketing banners, dealer watermark graphics, arrows, colored callouts, app screenshots,
collage layouts, or other design elements placed on top of the photo. Do not reject merely because text,
logos, navigation UI, or dealer names are visible inside the original camera photo.

Do NOT reject normal incidental text that is physically part of the vehicle or scene, including license plates
or plate frames. License plate and plate-frame text should be ignored even when it includes dealer names,
locations, slogans, phone numbers, or websites. Also allow dashboard gauges, odometer screens,
infotainment/navigation screens, GPS/MapQuest/map text visible on an in-car display, window stickers,
inspection stickers, tire labels, manufacturer logos, model/trim/emission/drive badges, emblems, decals
physically attached to the vehicle, or signs reflected in glass. Treat those as clean_vehicle_photo unless
there is also a clear added promotional overlay outside the physical plate/frame/display/object/vehicle badge.
When unsure whether text is physically in the scene or added after the photo, choose clean_vehicle_photo.

Use has_ui_or_screenshot_elements only when the whole image is a screenshot/composite UI rather than a camera
photo of a vehicle interior display.

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
    records: list[dict[str, Any]] = []
    model_jobs: list[tuple[int, str]] = []
    approved: list[str] = []

    for url in candidate_urls:
        key = canonical_source_image_url(url)
        asset = assets_by_key.get(key)
        record: dict[str, Any] = {
            "url": url,
            "asset": asset,
            "cached": False,
            "result": None,
        }
        records.append(record)

        cached = _cached_screening(asset)
        if cached:
            record["cached"] = True
            record["result"] = cached
            continue

        result = _cheap_precheck(url)
        if result is None:
            model_jobs.append((len(records) - 1, url))
        else:
            record["result"] = result

    parallelism = max(1, int(settings.image_screening_parallelism or 4))
    if model_jobs:
        with ThreadPoolExecutor(max_workers=min(parallelism, len(model_jobs))) as executor:
            futures = {executor.submit(_screen_with_models, url): index for index, url in model_jobs}
            for future in as_completed(futures):
                index = futures[future]
                try:
                    records[index]["result"] = future.result()
                except Exception as exc:
                    logger.info("image_screening_job_failed url=%s", records[index]["url"], exc_info=True)
                    records[index]["result"] = _failure_result("screening", str(exc))

    for record in records:
        url = str(record["url"])
        result = record["result"] or _failure_result("screening", "No screening result was produced.")
        asset = record["asset"]

        if asset:
            if not record["cached"]:
                metadata = dict(asset.metadata_json or {})
                metadata[SCREENING_CACHE_KEY] = result
                asset.metadata_json = metadata
            asset.active = bool(result.get("approved"))
        display_source_url = _asset_url(asset) if asset else url
        display_url = _display_url(display_source_url or url, result)
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
        if not key:
            continue
        current = out.get(key)
        if current is None:
            out[key] = asset
            continue
        current_screening = (current.metadata_json or {}).get(SCREENING_CACHE_KEY)
        asset_screening = (asset.metadata_json or {}).get(SCREENING_CACHE_KEY)
        if not current.active and asset.active:
            out[key] = asset
        elif not isinstance(current_screening, dict) and isinstance(asset_screening, dict):
            out[key] = asset
    return out


def _cached_screening(asset: VehicleImageAsset | None) -> dict[str, Any] | None:
    if not asset:
        return None
    screening = (asset.metadata_json or {}).get(SCREENING_CACHE_KEY)
    if not isinstance(screening, dict):
        return None
    if screening.get("admin_override") is True and isinstance(screening.get("approved"), bool):
        return screening
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
            confidence=0.92,
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
    overlay_types = _string_list(parsed.get("overlay_types"))
    visible_text = _string_list(parsed.get("visible_text"))
    reason = str(parsed.get("reason") or "")
    crop_salvage = (
        crop_recommendation != "none"
        and classification in SCREENING_CROP_CLASSIFICATIONS
        and confidence >= 0.65
    )
    approved = _approve_screening_result(
        classification=classification,
        has_overlay=has_overlay,
        overlay_types=overlay_types,
        visible_text=visible_text,
        crop_salvage=crop_salvage,
        confidence=confidence,
        reason=reason,
    )
    return _result(
        provider=provider,
        model=model,
        classification=classification,
        has_overlay=has_overlay,
        overlay_types=overlay_types,
        visible_text=visible_text,
        crop_recommendation=crop_recommendation,
        confidence=confidence,
        reason=reason,
        approved=approved,
    )


def _approve_screening_result(
    *,
    classification: str,
    has_overlay: bool,
    overlay_types: list[str],
    visible_text: list[str],
    crop_salvage: bool,
    confidence: float,
    reason: str,
) -> bool:
    if crop_salvage:
        return True
    if classification == "clean_vehicle_photo":
        return True
    if classification == "not_vehicle_photo":
        return confidence < 0.85

    marketing_signal = _has_marketing_signal(overlay_types=overlay_types, visible_text=visible_text, reason=reason)
    incidental_signal = _has_incidental_vehicle_text(visible_text=visible_text, reason=reason)
    plate_context = _has_license_plate_context(overlay_types=overlay_types, visible_text=visible_text, reason=reason)
    added_overlay_context = _has_added_overlay_context(overlay_types=overlay_types, visible_text=visible_text, reason=reason)
    non_vehicle_marketing = _has_non_vehicle_marketing_context(overlay_types=overlay_types, visible_text=visible_text, reason=reason)

    if non_vehicle_marketing and confidence >= 0.75:
        return False

    if classification in {"has_text_overlay", "has_graphic_overlay"}:
        if plate_context or incidental_signal:
            return True
        if marketing_signal and added_overlay_context and confidence >= 0.84:
            return False
        return True

    if classification == "has_ui_or_screenshot_elements":
        return not (marketing_signal and added_overlay_context and not incidental_signal and confidence >= 0.9)

    if classification == "uncertain":
        return True

    return not (has_overlay and marketing_signal and added_overlay_context and confidence >= 0.84)


def _has_marketing_signal(*, overlay_types: list[str], visible_text: list[str], reason: str) -> bool:
    haystack = " ".join([*overlay_types, *visible_text, reason])
    return bool(MARKETING_SIGNAL_RE.search(haystack))


def _has_incidental_vehicle_text(*, visible_text: list[str], reason: str) -> bool:
    haystack = " ".join([*visible_text, reason])
    return bool(INCIDENTAL_TEXT_RE.search(haystack))


def _has_license_plate_context(*, overlay_types: list[str], visible_text: list[str], reason: str) -> bool:
    haystack = " ".join([*overlay_types, *visible_text, reason])
    return bool(LICENSE_PLATE_CONTEXT_RE.search(haystack))


def _has_added_overlay_context(*, overlay_types: list[str], visible_text: list[str], reason: str) -> bool:
    haystack = " ".join([*overlay_types, *visible_text, reason])
    if NEGATED_ADDED_OVERLAY_RE.search(haystack):
        return False
    return bool(ADDED_OVERLAY_CONTEXT_RE.search(haystack))


def _has_non_vehicle_marketing_context(*, overlay_types: list[str], visible_text: list[str], reason: str) -> bool:
    haystack = " ".join([*overlay_types, *visible_text, reason])
    return bool(NON_VEHICLE_MARKETING_RE.search(haystack))


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
        has_overlay=False,
        overlay_types=["screening_failed"],
        visible_text=[],
        crop_recommendation="none",
        confidence=0.0,
        reason=reason,
        approved=True,
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
