from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class CreditTierDefinition:
    id: str
    label: str
    min_score: int
    max_score: int | None
    apr: float


DEFAULT_LOAN_TERM_MONTHS = 72
DEFAULT_CREDIT_TIER_ID = "A"

CREDIT_TIER_DEFINITIONS: tuple[CreditTierDefinition, ...] = (
    CreditTierDefinition(id="A+", label="750+", min_score=750, max_score=None, apr=6.95),
    CreditTierDefinition(id="A", label="720-749", min_score=720, max_score=749, apr=7.59),
    CreditTierDefinition(id="A-", label="700-719", min_score=700, max_score=719, apr=8.50),
    CreditTierDefinition(id="B+", label="680-699", min_score=680, max_score=699, apr=9.50),
    CreditTierDefinition(id="B-", label="640-679", min_score=640, max_score=679, apr=10.75),
    CreditTierDefinition(id="C+", label="620-639", min_score=620, max_score=639, apr=12.49),
    CreditTierDefinition(id="C", label="600-619", min_score=600, max_score=619, apr=14.49),
    CreditTierDefinition(id="D", label="550-599", min_score=550, max_score=599, apr=19.42),
    CreditTierDefinition(id="F", label="Below 550", min_score=0, max_score=549, apr=21.85),
)

_CREDIT_TIER_MAP = {tier.id.upper(): tier for tier in CREDIT_TIER_DEFINITIONS}


def _round_money(value: float) -> float:
    return round(float(value or 0) + 1e-9, 2)


def get_credit_tier_definition(tier_id: str | None) -> CreditTierDefinition:
    normalized = (tier_id or "").strip().upper()
    return _CREDIT_TIER_MAP.get(normalized, _CREDIT_TIER_MAP[DEFAULT_CREDIT_TIER_ID])


def estimate_monthly_payment(principal: float, annual_rate: float, months: int = DEFAULT_LOAN_TERM_MONTHS) -> float:
    normalized_principal = max(float(principal or 0), 0.0)
    normalized_months = max(int(months or 0), 0)
    if normalized_principal <= 0 or normalized_months <= 0:
        return 0.0

    monthly_rate = annual_rate / 100 / 12
    if monthly_rate <= 0:
        return _round_money(normalized_principal / normalized_months)

    factor = (1 + monthly_rate) ** normalized_months
    payment = normalized_principal * ((monthly_rate * factor) / (factor - 1))
    return _round_money(payment)


def build_payment_estimate(principal: float, tier_id: str | None, months: int = DEFAULT_LOAN_TERM_MONTHS) -> dict[str, object]:
    tier = get_credit_tier_definition(tier_id)
    normalized_principal = _round_money(principal)
    normalized_months = max(int(months or DEFAULT_LOAN_TERM_MONTHS), 1)

    return {
        "principal": normalized_principal,
        "months": normalized_months,
        "apr": tier.apr,
        "monthly_payment": estimate_monthly_payment(normalized_principal, tier.apr, normalized_months),
        "credit_tier": asdict(tier),
    }
