from __future__ import annotations

import hashlib
import html
import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

from app.core.config import settings
from app.models.entities import Vehicle

logger = logging.getLogger(__name__)

SELLER_COMMENT_CACHE_KEY = "seller_comment_rewrite"
SELLER_COMMENT_CACHE_VERSION = 2
OPENAI_MODEL = "gpt-5.4-mini-2026-03-17"
ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
_PHONE_RE = re.compile(r"(?:\+?1[\s.\-]?)?(?:\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})")
_WHITESPACE_RE = re.compile(r"\s+")
_MARKDOWN_FENCE_RE = re.compile(r"^```(?:\w+)?\s*|\s*```$", re.MULTILINE)
_MARKDOWN_HEADING_RE = re.compile(r"^\s*#+\s*", re.MULTILINE)
_MILEAGE_RE = re.compile(r"\b\d[\d,]*\s*(?:miles?|mi)\b", re.IGNORECASE)
_PRICE_RE = re.compile(r"\$\s*\d[\d,]*(?:\.\d+)?")
_ZIP_RE = re.compile(r"\b\d{5}(?:-\d{4})?\b")
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")

_BANNED_SENTENCE_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bcall\b",
        r"\btext\b",
        r"\bcontact us\b",
        r"\bvisit us\b",
        r"\btest drive\b",
        r"\bapply now\b",
        r"\bshop now\b",
        r"\bact now\b",
        r"\bthis vehicle won['’]t last\b",
        r"\blimited time\b",
        r"\bfinancing\b",
        r"\bmonthly payment\b",
        r"\btrade[- ]in\b",
        r"\bwarranty\b",
        r"\bdealer\b",
        r"\bdealership\b",
        r"\bcarfax\b",
        r"\bautocheck\b",
        r"\bshipping available\b",
        r"\bdelivery available\b",
        r"\bmust see\b",
        r"\bpriced to sell\b",
        r"\bonly at\b",
    )
]


def _to_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_whitespace(value: str | None) -> str:
    text = _to_str(value) or ""
    if not text:
        return ""
    return _WHITESPACE_RE.sub(" ", text).strip()


def _strip_contact_details(value: str | None) -> str:
    text = _normalize_whitespace(value)
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = _URL_RE.sub(" ", text)
    text = _EMAIL_RE.sub(" ", text)
    text = _PHONE_RE.sub(" ", text)
    return _normalize_whitespace(text)


def _clean_source_comment(value: str | None) -> str:
    text = _strip_contact_details(value)
    if not text:
        return ""

    sentences = []
    for raw_sentence in _SENTENCE_SPLIT_RE.split(text):
        sentence = _normalize_whitespace(raw_sentence)
        if not sentence:
            continue
        if any(pattern.search(sentence) for pattern in _BANNED_SENTENCE_PATTERNS):
            continue
        sentences.append(sentence)

    return _normalize_whitespace(" ".join(sentences))


def _fingerprint_source_comment(value: str | None) -> str:
    normalized = _clean_source_comment(value) or _normalize_whitespace(value)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _vehicle_context(vehicle: Vehicle, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    metadata = metadata or {}
    normalized = vehicle.features_normalized or {}
    return {
        "year": vehicle.year,
        "make": vehicle.make,
        "model": vehicle.model,
        "trim": vehicle.trim,
        "body_type": vehicle.body_type,
        "drivetrain": vehicle.drivetrain,
        "engine_type": vehicle.engine_type,
        "exterior_color": normalized.get("exterior_color") or metadata.get("exterior_color"),
        "interior_color": normalized.get("interior_color") or metadata.get("interior_color"),
        "fuel_type": metadata.get("fuel_type") or normalized.get("fuel_type"),
        "transmission": metadata.get("transmission") or normalized.get("transmission"),
    }


def _top_feature_highlights(metadata: dict[str, Any] | None = None, *, limit: int = 5) -> list[str]:
    metadata = metadata or {}
    ordered_sources = (
        metadata.get("high_value_features") or [],
        metadata.get("option_packages") or [],
        metadata.get("options") or [],
        metadata.get("features") or [],
    )
    out: list[str] = []
    seen: set[str] = set()
    for source in ordered_sources:
        for raw in source:
            text = _to_str(raw)
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
            if len(out) >= limit:
                return out
    return out


def _finalize_rewritten_comment(value: str | None) -> str | None:
    text = _to_str(value)
    if not text:
        return None
    text = _MARKDOWN_FENCE_RE.sub("", text)
    text = _MARKDOWN_HEADING_RE.sub("", text)
    text = _strip_contact_details(text)
    if not text:
        return None

    safe_sentences: list[str] = []
    for raw_sentence in _SENTENCE_SPLIT_RE.split(text):
        sentence = _normalize_whitespace(raw_sentence)
        if not sentence:
            continue
        if _URL_RE.search(sentence) or _EMAIL_RE.search(sentence) or _PHONE_RE.search(sentence):
            continue
        if _MILEAGE_RE.search(sentence):
            continue
        if _PRICE_RE.search(sentence):
            continue
        if _ZIP_RE.search(sentence):
            continue
        if any(pattern.search(sentence) for pattern in _BANNED_SENTENCE_PATTERNS):
            continue
        safe_sentences.append(sentence.rstrip(".") + ".")
        if len(safe_sentences) >= 4:
            break

    if not safe_sentences:
        return None
    if not any("virtual carhub" in sentence.lower() for sentence in safe_sentences):
        if len(safe_sentences) >= 4:
            safe_sentences = safe_sentences[:3]
        safe_sentences.append("Presented through Virtual CarHub.")
    return " ".join(safe_sentences)


def _fallback_rewrite(vehicle: Vehicle, source_text: str | None, metadata: dict[str, Any] | None = None) -> str | None:
    cleaned = _clean_source_comment(source_text)
    if not cleaned:
        return None

    context = _vehicle_context(vehicle, metadata)
    feature_highlights = _top_feature_highlights(metadata, limit=4)

    name_parts = [str(context["year"]), context["make"], context["model"]]
    if context.get("trim"):
        name_parts.append(str(context["trim"]))
    vehicle_name = " ".join(part for part in name_parts if part)

    descriptors = []
    if context.get("body_type"):
        descriptors.append(str(context["body_type"]))
    if context.get("drivetrain"):
        descriptors.append(str(context["drivetrain"]))
    if context.get("exterior_color"):
        descriptors.append(f"{context['exterior_color']} exterior")
    if context.get("interior_color"):
        descriptors.append(f"{context['interior_color']} interior")

    opening = f"Virtual CarHub is presenting this {vehicle_name}"
    if descriptors:
        opening += f" with {' and '.join(descriptors[:2])}"
    opening += "."

    middle = ""
    if feature_highlights:
        if len(feature_highlights) == 1:
            middle = f"Notable equipment includes {feature_highlights[0]}."
        else:
            middle = f"Notable equipment includes {', '.join(feature_highlights[:-1])}, and {feature_highlights[-1]}."

    closing = "This summary is tailored for Virtual CarHub from available source listing details."
    return _finalize_rewritten_comment(" ".join(part for part in (opening, middle, closing) if part))


def _build_rewrite_prompt(vehicle: Vehicle, source_text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    cleaned = _clean_source_comment(source_text)
    context = _vehicle_context(vehicle, metadata)
    feature_highlights = _top_feature_highlights(metadata, limit=8)
    return {
        "vehicle": context,
        "feature_highlights": feature_highlights,
        "source_comment": (cleaned or "")[:2400],
        "instructions": [
            "Rewrite the source comment as a short Virtual CarHub listing description.",
            "Write 2 to 4 sentences in a polished, neutral, trustworthy tone.",
            "Mention Virtual CarHub once.",
            "Do not include a title or heading.",
            "Do not mention dealer names, dealership locations, websites, phone numbers, financing, trade-ins, warranties, or limited-time sales language.",
            "Do not mention mileage, odometer, price, monthly payment, or any number that is not explicitly included in the provided vehicle facts.",
            "Do not invent condition claims, ownership history, or package details that are not supported by the provided data.",
            "Keep the focus on the vehicle and its notable equipment.",
            "Return plain text only.",
        ],
    }


_REWRITE_SYSTEM = "You rewrite dealer vehicle descriptions into concise Virtual CarHub marketing copy while preserving factual accuracy."


def _openai_rewrite(vehicle: Vehicle, source_text: str, metadata: dict[str, Any] | None = None) -> str | None:
    import httpx

    cleaned = _clean_source_comment(source_text)
    if not cleaned:
        return None

    prompt = _build_rewrite_prompt(vehicle, source_text, metadata)
    payload = {
        "model": OPENAI_MODEL,
        "input": [
            {"role": "system", "content": _REWRITE_SYSTEM},
            {"role": "user", "content": json.dumps(prompt, ensure_ascii=True)},
        ],
    }
    with httpx.Client(timeout=30.0) as client:
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

    text = data.get("output_text") or ""
    if not text:
        for output in data.get("output", []):
            if not isinstance(output, dict):
                continue
            for content in output.get("content", []):
                if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                    text += content.get("text", "")
    return _finalize_rewritten_comment(text.strip())


def _anthropic_rewrite(vehicle: Vehicle, source_text: str, metadata: dict[str, Any] | None = None) -> str | None:
    import anthropic

    cleaned = _clean_source_comment(source_text)
    if not cleaned:
        return None

    prompt = _build_rewrite_prompt(vehicle, source_text, metadata)
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model=ANTHROPIC_MODEL,
        max_tokens=220,
        temperature=0.2,
        system=_REWRITE_SYSTEM,
        messages=[{"role": "user", "content": json.dumps(prompt, ensure_ascii=True)}],
    )
    parts = getattr(message, "content", None) or []
    text = "".join(getattr(part, "text", "") for part in parts).strip()
    return _finalize_rewritten_comment(text)


def _llm_rewrite(vehicle: Vehicle, source_text: str, metadata: dict[str, Any] | None = None) -> str | None:
    """Try OpenAI first, fall back to Anthropic."""
    if settings.has_openai:
        try:
            result = _openai_rewrite(vehicle, source_text, metadata)
            if result:
                return result
        except Exception:
            logger.warning("seller_comment_openai_rewrite_failed vin=%s, falling back to anthropic", vehicle.vin, exc_info=True)

    if settings.has_anthropic:
        return _anthropic_rewrite(vehicle, source_text, metadata)

    return None


def build_virtualcarhub_seller_comment(
    *,
    vehicle: Vehicle,
    source_text: str | None,
    metadata: dict[str, Any] | None = None,
) -> tuple[str | None, str]:
    cleaned = _clean_source_comment(source_text)
    if not cleaned:
        return None, "empty"

    if settings.has_openai or settings.has_anthropic:
        try:
            rewritten = _llm_rewrite(vehicle, cleaned, metadata)
            if rewritten:
                return rewritten, "llm"
        except Exception:
            logger.warning("seller_comment_llm_rewrite_failed vin=%s", vehicle.vin, exc_info=True)

    return _fallback_rewrite(vehicle, cleaned, metadata), "fallback"


def get_cached_vehicle_seller_comment(vehicle: Vehicle, source_text: str | None) -> str | None:
    normalized = vehicle.features_normalized or {}
    cache = normalized.get(SELLER_COMMENT_CACHE_KEY)
    if not isinstance(cache, dict):
        return None
    if int(cache.get("version") or 0) != SELLER_COMMENT_CACHE_VERSION:
        return None
    if cache.get("source_fingerprint") != _fingerprint_source_comment(source_text):
        return None
    return _to_str(cache.get("text"))


def cache_vehicle_seller_comment(
    vehicle: Vehicle,
    *,
    source_text: str | None,
    rewritten_text: str | None,
    provider: str,
    source_kind: str,
) -> bool:
    text = _to_str(rewritten_text)
    if not text:
        return False

    normalized = dict(vehicle.features_normalized or {})
    payload = {
        "version": SELLER_COMMENT_CACHE_VERSION,
        "source_fingerprint": _fingerprint_source_comment(source_text),
        "text": text,
        "provider": provider,
        "source_kind": source_kind,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    if normalized.get(SELLER_COMMENT_CACHE_KEY) == payload:
        return False
    normalized[SELLER_COMMENT_CACHE_KEY] = payload
    vehicle.features_normalized = normalized
    return True
