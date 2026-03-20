"""Natural-language vehicle query parser.

Uses Claude API to extract structured search filters from free-text input.
Falls back to regex-based extraction when no API key is configured or
when the LLM call fails.
"""

from __future__ import annotations

import json
import logging
import re

from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger("vch.nlp_query")

# ── Pydantic response model ─────────────────────────────────────────

class ParsedVehicleQuery(BaseModel):
    make: str | None = None
    model: str | None = None
    trim: str | None = None
    body_type: str | None = None
    min_year: int | None = None
    max_year: int | None = None
    min_price: float | None = None
    max_price: float | None = None
    min_miles: int | None = None
    max_miles: int | None = None
    exterior_color: str | None = None
    drivetrain: str | None = None
    fuel_type: str | None = None
    transmission: str | None = None
    state: str | None = None
    certified: bool | None = None
    single_owner: bool | None = None
    clean_title: bool | None = None
    raw_query: str = ""
    parsed: bool = False
    parse_method: str = "none"  # "llm", "fallback", "none"


# ── System prompt for Claude ─────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a vehicle search filter extractor. Given a natural language vehicle \
description, extract structured search filters. Return ONLY valid JSON — no \
markdown, no explanation — with these optional fields:

  make            — e.g. "BMW", "Toyota"
  model           — e.g. "X5", "Camry"
  trim            — e.g. "xDrive40i", "Limited"
  body_type       — one of: sedan, suv, truck, coupe, convertible, van, wagon, hatchback
  min_year        — integer
  max_year        — integer
  min_price       — number (dollars)
  max_price       — number (dollars)
  min_miles       — integer
  max_miles       — integer
  exterior_color  — e.g. "black", "white"
  drivetrain      — one of: AWD, FWD, RWD, 4WD
  fuel_type       — one of: gasoline, diesel, electric, hybrid
  transmission    — one of: automatic, manual
  state           — 2-letter US state code
  certified       — boolean
  single_owner    — boolean
  clean_title     — boolean

Rules:
- Omit any field not mentioned or implied by the user.
- For "under X miles" → set max_miles = X.
- For "under $X" or "budget X" → set max_price = X.
- For "around $30k" → set min_price = 27000, max_price = 33000.
- For a single year like "2021" → set both min_year and max_year to 2021.
- For "newer than 2020" → set min_year = 2021.
- Convert shorthand: "40k" = 40000, "$30k" = 30000.
- Return {} if the input is not a vehicle query.
"""


# ── Main entry point ─────────────────────────────────────────────────

def parse_vehicle_query(query: str) -> ParsedVehicleQuery:
    """Parse a natural-language vehicle query into structured filters."""
    clean = query.strip()
    if not clean:
        return ParsedVehicleQuery(raw_query=query)

    if settings.has_anthropic:
        try:
            return _llm_parse(clean)
        except Exception as exc:
            logger.warning("llm_parse_failed, falling back to regex", extra={"error": str(exc)})

    return _fallback_parse(clean)


# ── LLM-based parser ─────────────────────────────────────────────────

def _llm_parse(query: str) -> ParsedVehicleQuery:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=300,
        temperature=0,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": query}],
    )

    raw_text = message.content[0].text.strip()
    # Strip markdown fences if the model wraps them
    if raw_text.startswith("```"):
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)

    data = json.loads(raw_text)
    if not isinstance(data, dict):
        raise ValueError("LLM returned non-object JSON")

    return ParsedVehicleQuery(
        **{k: v for k, v in data.items() if k in ParsedVehicleQuery.model_fields},
        raw_query=query,
        parsed=True,
        parse_method="llm",
    )


# ── Regex fallback parser ────────────────────────────────────────────

_KNOWN_MAKES = {
    "acura", "alfa romeo", "aston martin", "audi", "bentley", "bmw", "buick",
    "cadillac", "chevrolet", "chevy", "chrysler", "dodge", "ferrari", "fiat",
    "ford", "genesis", "gmc", "honda", "hyundai", "infiniti", "jaguar", "jeep",
    "kia", "lamborghini", "land rover", "lexus", "lincoln", "lotus", "lucid",
    "maserati", "mazda", "mclaren", "mercedes", "mercedes-benz", "mini",
    "mitsubishi", "nissan", "polestar", "porsche", "ram", "rivian", "rolls-royce",
    "subaru", "suzuki", "tesla", "toyota", "volkswagen", "volvo",
}

_MAKE_ALIASES = {"chevy": "Chevrolet", "mercedes": "Mercedes-Benz"}

_YEAR_RE = re.compile(r"\b((?:19|20)\d{2})\b")
_PRICE_RE = re.compile(r"\$\s*([\d,]+)\s*k?\b|\b([\d]+)\s*k\b", re.IGNORECASE)
_MILES_RE = re.compile(r"\b([\d,]+\s*k?)\s*miles?\b", re.IGNORECASE)
_UNDER_OVER_RE = re.compile(r"\b(under|below|less than|max|up to|over|above|more than|at least|min)\b", re.IGNORECASE)


def _parse_number(raw: str) -> int:
    """Convert '40k' / '40,000' / '40000' style strings to int."""
    cleaned = raw.replace(",", "").strip()
    if cleaned.lower().endswith("k"):
        return int(float(cleaned[:-1]) * 1000)
    return int(float(cleaned))


def _fallback_parse(query: str) -> ParsedVehicleQuery:
    result = ParsedVehicleQuery(raw_query=query, parsed=True, parse_method="fallback")
    lower = query.lower()
    tokens = query.split()

    # ── Year ──
    year_matches = _YEAR_RE.findall(lower)
    years = [int(y) for y in year_matches if 1990 <= int(y) <= 2030]
    if len(years) == 1:
        result.min_year = years[0]
        result.max_year = years[0]
    elif len(years) >= 2:
        result.min_year = min(years)
        result.max_year = max(years)

    # ── Make ──
    for i, token in enumerate(tokens):
        token_lower = token.lower().rstrip(".,;:!?")
        if token_lower in _KNOWN_MAKES:
            result.make = _MAKE_ALIASES.get(token_lower, token.rstrip(".,;:!?").title())
            # Next token is likely the model
            if i + 1 < len(tokens):
                candidate = tokens[i + 1].rstrip(".,;:!?")
                # Skip if it looks like a year or common filler
                if not _YEAR_RE.match(candidate) and candidate.lower() not in {
                    "with", "under", "below", "above", "over", "and", "or", "for",
                }:
                    result.model = candidate
            break

    # ── Mileage ──
    miles_match = _MILES_RE.search(query)
    if miles_match:
        miles_val = _parse_number(miles_match.group(1))
        # Check for "under/over" before the number
        prefix_region = query[: miles_match.start()].split()[-3:] if miles_match.start() > 0 else []
        prefix_text = " ".join(prefix_region).lower()
        if any(w in prefix_text for w in ("under", "below", "less", "max", "up to")):
            result.max_miles = miles_val
        elif any(w in prefix_text for w in ("over", "above", "more", "at least", "min")):
            result.min_miles = miles_val
        else:
            result.max_miles = miles_val  # default to max

    # ── Price ──
    for price_match in _PRICE_RE.finditer(query):
        raw_val = price_match.group(1) or price_match.group(2)
        price_val = _parse_number(raw_val)
        # If the original match had a trailing 'k' in the dollar form, multiply
        match_text = price_match.group(0)
        if "$" in match_text and match_text.lower().endswith("k"):
            price_val = int(float(raw_val.replace(",", "")) * 1000)

        prefix_region = query[: price_match.start()].split()[-3:]
        prefix_text = " ".join(prefix_region).lower()
        if any(w in prefix_text for w in ("under", "below", "less", "max", "up to", "budget")):
            result.max_price = price_val
        elif any(w in prefix_text for w in ("over", "above", "more", "at least", "min")):
            result.min_price = price_val
        elif "around" in prefix_text or "about" in prefix_text:
            result.min_price = int(price_val * 0.9)
            result.max_price = int(price_val * 1.1)
        else:
            result.max_price = price_val

    # ── Body type ──
    body_types = {
        "sedan": "sedan", "suv": "suv", "truck": "truck", "coupe": "coupe",
        "convertible": "convertible", "van": "van", "wagon": "wagon",
        "hatchback": "hatchback", "pickup": "truck", "minivan": "van",
        "crossover": "suv",
    }
    for keyword, body in body_types.items():
        if keyword in lower:
            result.body_type = body
            break

    # ── Drivetrain ──
    for dt in ("awd", "4wd", "fwd", "rwd", "all-wheel", "four-wheel"):
        if dt in lower:
            mapped = {"all-wheel": "AWD", "four-wheel": "4WD"}.get(dt, dt.upper())
            result.drivetrain = mapped
            break

    # ── Fuel type ──
    for ft in ("electric", "hybrid", "diesel", "ev"):
        if ft in lower:
            result.fuel_type = "electric" if ft == "ev" else ft
            break

    return result
