from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

import httpx

from app.core.config import settings
from app.schemas.condition_report_granular import (
    allowed_granular_field_paths,
    apply_granular_ai_patches,
    build_granular_condition_report,
)

logger = logging.getLogger(__name__)

OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"


AI_REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "patches": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "field_path": {"type": "string"},
                    "status": {"type": "string", "enum": ["normal", "issue", "unknown"]},
                    "value": {"type": "string"},
                    "evidence": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "reason": {"type": "string"},
                },
                "required": ["field_path", "status", "value", "evidence", "confidence", "reason"],
            },
        },
        "warnings": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["patches", "warnings"],
}


def ai_review_configured() -> bool:
    return settings.openai_cr_review_mode != "disabled" and bool(settings.openai_api_key)


def review_condition_report_with_ai(
    report: dict[str, Any],
    *,
    vehicle: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Review a normalized condition report and apply high-confidence AI patches.

    The model never creates the report from scratch. It receives the deterministic
    granular report plus source text and may only return patches against allowed
    field paths. Patches need evidence and must pass confidence thresholds.
    """
    if not settings.openai_api_key:
        return _with_review_metadata(report, status="skipped", reason="missing_openai_api_key")

    base_report = dict(report)
    if "granular_inspection" not in base_report:
        base_report["granular_inspection"] = build_granular_condition_report(base_report)

    review_input = _build_review_input(base_report, vehicle=vehicle)
    if not _has_reviewable_source(review_input):
        return _with_review_metadata(base_report, status="skipped", reason="no_reviewable_source")

    payload = {
        "model": settings.openai_cr_review_model,
        "input": [
            {
                "role": "system",
                "content": _system_instructions(),
            },
            {
                "role": "user",
                "content": json.dumps(review_input, ensure_ascii=False),
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "condition_report_ai_review",
                "schema": AI_REVIEW_SCHEMA,
                "strict": True,
            }
        },
    }

    try:
        response_data = _post_openai_response(payload)
        parsed = _extract_json_response(response_data)
    except Exception as exc:
        logger.warning("condition_report_ai_review_failed: %s", exc, exc_info=True)
        return _with_review_metadata(base_report, status="failed", reason=str(exc)[:300])

    patches = parsed.get("patches") if isinstance(parsed, dict) else None
    if not isinstance(patches, list):
        return _with_review_metadata(base_report, status="failed", reason="missing_patches_array")

    updated, accepted = apply_granular_ai_patches(
        base_report,
        patches,
        auto_apply_confidence=settings.openai_cr_review_auto_apply_confidence,
    )
    metadata = {
        "status": "completed",
        "reviewed_at": datetime.now(UTC).isoformat(),
        "model": settings.openai_cr_review_model,
        "input_hash": review_input["input_hash"],
        "patches_proposed": len(patches),
        "patches_accepted": len(accepted),
        "accepted_patches": accepted,
        "warnings": parsed.get("warnings") if isinstance(parsed.get("warnings"), list) else [],
    }
    return _with_review_metadata(updated, **metadata)


def _post_openai_response(payload: dict[str, Any]) -> dict[str, Any]:
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
        return response.json()


def _extract_json_response(response_data: dict[str, Any]) -> dict[str, Any]:
    chunks: list[str] = []
    for output in response_data.get("output", []):
        if not isinstance(output, dict):
            continue
        for content in output.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    if not chunks and isinstance(response_data.get("output_text"), str):
        chunks.append(response_data["output_text"])
    text = "".join(chunks).strip()
    if not text:
        raise ValueError("OpenAI response contained no text output")
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("OpenAI response was not a JSON object")
    return parsed


def _build_review_input(report: dict[str, Any], *, vehicle: dict[str, Any] | None) -> dict[str, Any]:
    source = {
        "vehicle": vehicle or {},
        "allowed_field_paths": allowed_granular_field_paths(),
        "granular_inspection": report.get("granular_inspection") or {},
        "damage_items": _bounded(report.get("damage_items"), 5000),
        "problem_highlights": _bounded(report.get("problem_highlights"), 2500),
        "remarks": _bounded(report.get("remarks"), 2500),
        "seller_comments_items": _bounded(report.get("seller_comments_items"), 2500),
        "seller_comments": _bounded(report.get("seller_comments"), 1500),
        "announcements": _bounded(report.get("announcements"), 2000),
        "tire_depths": report.get("tire_depths") or {},
        "inspection": _bounded(report.get("inspection"), 6500),
        "raw_text": _bounded(report.get("raw_text"), settings.openai_cr_review_input_char_limit),
        "report_body_text": _bounded(
            (((report.get("metadata") or {}).get("report_page") or {}).get("body_text"))
            if isinstance(report.get("metadata"), dict)
            else None,
            settings.openai_cr_review_input_char_limit,
        ),
    }
    serialized = json.dumps(source, sort_keys=True, default=str)
    source["input_hash"] = sha256(serialized.encode("utf-8")).hexdigest()
    return source


def _has_reviewable_source(review_input: dict[str, Any]) -> bool:
    for key in ("damage_items", "problem_highlights", "remarks", "seller_comments_items", "seller_comments", "raw_text", "report_body_text"):
        value = review_input.get(key)
        if value not in (None, "", [], {}):
            return True
    return False


def _bounded(value: Any, limit: int) -> Any:
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, list):
        out: list[Any] = []
        used = 0
        for item in value:
            text = json.dumps(item, default=str) if not isinstance(item, str) else item
            used += len(text)
            if used > limit:
                break
            out.append(item)
        return out
    if isinstance(value, dict):
        text = json.dumps(value, default=str)
        if len(text) <= limit:
            return value
        return {"truncated_json": text[:limit]}
    return value


def _system_instructions() -> str:
    return (
        "You review vehicle condition report data for VirtualCarHub. "
        "Return JSON only using the provided schema. You may only propose patches for allowed_field_paths. "
        "Do not infer title, accident, odometer, structural, or safety facts without direct source evidence. "
        "Only mark a granular field as issue when source text explicitly reports damage, malfunction, odor, warning light, leak, tire/wheel issue, or similar problem. "
        "Use evidence as a short exact source phrase. Prefer the most specific field. "
        "If location is ambiguous, use exterior.further_disclosures or warnings instead of guessing. "
        "For clean/default fields, usually return no patch; the deterministic report already says Normal - No Damage Reported or Normal - No Issue Reported. "
        "IMPORTANT: The body_text may contain a 'Repaired' section listing items with 'Repair Status: Completed'. "
        "These are historical repairs and do NOT represent current damage — do NOT mark the corresponding panel as 'issue'. "
        "Similarly, damage_items with section_label 'Repaired' or repair_status 'completed'/'repaired' are already fixed."
    )


def _with_review_metadata(report: dict[str, Any], **values: Any) -> dict[str, Any]:
    updated = dict(report)
    metadata = dict(updated.get("ai_review") or {})
    metadata.update(values)
    metadata.setdefault("reviewed_at", datetime.now(UTC).isoformat())
    metadata.setdefault("model", settings.openai_cr_review_model)
    updated["ai_review"] = metadata
    return updated
