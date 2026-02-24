from __future__ import annotations

from math import exp

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.constants import ProfileTier
from app.models.entities import BuyerProfile, Deal, Vehicle, VehicleMatch
from app.services.profile_service import normalized_list, quick_priority_keywords


def run_matching(db: Session, *, profile: BuyerProfile, deal: Deal, limit: int = 10) -> list[VehicleMatch]:
    hard = profile.hard_constraints or {}
    excluded_brands = set(normalized_list(hard.get("brands_excluded", [])))

    vehicles = db.scalars(select(Vehicle).where(Vehicle.available.is_(True))).all()
    candidates: list[tuple[Vehicle, float, str]] = []

    for vehicle in vehicles:
        if vehicle.make.lower() in excluded_brands:
            continue
        if profile.profile_tier == ProfileTier.QUICK:
            score, explain = _quick_score(vehicle, profile.bfv_json)
        else:
            score, explain = _full_score(vehicle, profile.bfv_json)

        if score > 0:
            candidates.append((vehicle, score, explain))

    candidates.sort(key=lambda item: item[1], reverse=True)
    top = candidates[:limit]

    db.execute(delete(VehicleMatch).where(VehicleMatch.deal_id == deal.id))

    results: list[VehicleMatch] = []
    for vehicle, score, explain in top:
        transport = 850.0
        registration = 450.0
        vch_fee = 1295.0
        retail = vehicle.price_asking * 1.12
        estimated_otd = vehicle.price_asking + transport + registration + vch_fee
        match = VehicleMatch(
            deal_id=deal.id,
            user_id=deal.user_id,
            vin=vehicle.vin,
            match_score=round(score, 4),
            explainability_text=explain,
            estimated_transport_cost=transport,
            estimated_registration=registration,
            vch_fee=vch_fee,
            marketcheck_retail=round(retail, 2),
            estimated_otd=round(estimated_otd, 2),
            danny_savings=round(retail - estimated_otd, 2),
        )
        db.add(match)
        results.append(match)

    db.flush()
    return results


def _quick_score(vehicle: Vehicle, bfv: dict) -> tuple[float, str]:
    body_types = normalized_list(bfv.get("body_types_included", []))
    budget_min = float(bfv.get("budget_min", 0) or 0)
    budget_max = float(bfv.get("budget_max", 1000000) or 1000000)
    priorities = normalized_list(bfv.get("top_3_priorities", []))
    brand_included = normalized_list(bfv.get("brands_included", []))

    body_match = 1.0 if vehicle.body_type and vehicle.body_type.lower() in body_types else 0.35

    if budget_min <= vehicle.price_asking <= budget_max:
        budget_fit = 1.0
    else:
        center = (budget_min + budget_max) / 2 if budget_max > budget_min else budget_max
        distance = abs(vehicle.price_asking - center)
        budget_fit = max(0.0, exp(-distance / 12000))

    feature_text = " ".join(
        [
            *[str(f).lower() for f in (vehicle.features_raw or [])],
            *[str(k).lower() for k in (vehicle.features_normalized or {}).keys()],
            (vehicle.engine_type or "").lower(),
            (vehicle.drivetrain or "").lower(),
        ]
    )
    keywords = quick_priority_keywords(priorities)
    if keywords:
        hits = sum(1 for kw in keywords if kw in feature_text)
        priority_alignment = min(1.0, hits / max(1, len(keywords) * 0.4))
    else:
        priority_alignment = 0.6

    if brand_included:
        brand_preference = 1.0 if vehicle.make.lower() in brand_included else 0.2
    else:
        brand_preference = 0.65

    score = (
        body_match * 0.30
        + budget_fit * 0.30
        + priority_alignment * 0.25
        + brand_preference * 0.15
    )

    confidence = "Great Match" if score >= 0.8 else "Good Match"
    explain = (
        f"{confidence}: {vehicle.year} {vehicle.make} {vehicle.model} aligns with your body type, "
        "budget, and stated priorities."
    )
    return score, explain


def _full_score(vehicle: Vehicle, bfv: dict) -> tuple[float, str]:
    importance = bfv.get("category_importance_weights", {}) if isinstance(bfv, dict) else {}
    scores = vehicle.bfv_compatibility_scores or {}

    weighted_total = 0.0
    total_weight = 0.0

    if isinstance(importance, dict) and importance:
        for category, weight in importance.items():
            w = max(0.0, min(1.0, float(weight)))
            total_weight += w
            weighted_total += w * float(scores.get(category, 0.5))
    else:
        weighted_total = 0.62
        total_weight = 1.0

    base = weighted_total / total_weight if total_weight > 0 else 0.0

    if vehicle.quality_firewall_pass is False:
        return 0.0, "Excluded due to quality firewall."

    explain = (
        f"Strong fit for your full profile across key preference categories. "
        f"Quality grade: {vehicle.condition_grade or 'Unknown'}; drivetrain: {vehicle.drivetrain or 'N/A'}."
    )
    return base, explain
