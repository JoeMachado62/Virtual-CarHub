from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.constants import ProfileTier
from app.models.entities import BuyerProfile
from app.schemas.profile import ProfileUpdateRequest, QuickMatchRequest


QUICK_PRIORITY_FEATURE_MAP = {
    "fuel economy": ["fuel economy", "mpg", "hybrid", "ev"],
    "safety": ["safety", "blind spot", "lane keep", "collision"],
    "tech": ["carplay", "android auto", "navigation", "wifi"],
    "towing": ["tow", "trailer"],
    "luxury": ["leather", "premium", "sunroof"],
    "sportiness": ["sport", "turbo", "manual"],
    "cargo": ["cargo", "third row", "fold-flat"],
    "off-road": ["awd", "4wd", "off-road"],
}


def get_or_create_profile(db: Session, user_id: str) -> BuyerProfile:
    profile = db.scalar(select(BuyerProfile).where(BuyerProfile.user_id == user_id).limit(1))
    if profile:
        return profile

    profile = BuyerProfile(user_id=user_id)
    db.add(profile)
    db.flush()
    return profile


def apply_quick_match(profile: BuyerProfile, payload: QuickMatchRequest) -> BuyerProfile:
    quick_bfv = {
        "profile_tier": ProfileTier.QUICK.value,
        "body_types_included": payload.body_types_included,
        "budget_min": payload.budget_min,
        "budget_max": payload.budget_max,
        "year_min": payload.year_min,
        "year_max": payload.year_max,
        "mileage_min": payload.mileage_min,
        "mileage_max": payload.mileage_max,
        "top_3_priorities": payload.top_3_priorities,
        "brands_included": payload.brands_included,
        "brands_excluded": payload.brands_excluded,
        "delivery_zip": payload.delivery_zip,
        "notification_preferences": {
            "in_app": payload.notify_new_matches_in_app,
            "email": payload.notify_new_matches_email,
            "sms": payload.notify_new_matches_sms,
        },
        "weights": {
            "body_type": 0.20,
            "budget": 0.20,
            "year_fit": 0.15,
            "mileage_fit": 0.15,
            "priority_alignment": 0.15,
            "brand_preference": 0.15,
        },
    }

    profile.profile_tier = ProfileTier.QUICK
    profile.bfv_json = quick_bfv
    profile.hard_constraints = {
        "brands_excluded": payload.brands_excluded,
    }
    profile.intake_steps_complete = ["QM-1", "QM-2", "QM-3", "QM-4", "QM-5"]
    profile.is_complete = True
    profile.version += 1
    return profile


def apply_full_profile(profile: BuyerProfile, payload: ProfileUpdateRequest) -> BuyerProfile:
    profile.profile_tier = payload.profile_tier
    profile.bfv_json = payload.bfv_json
    profile.intake_steps_complete = payload.intake_steps_complete
    profile.hard_constraints = payload.hard_constraints
    profile.demographics = payload.demographics
    profile.is_complete = payload.is_complete
    profile.version += 1
    return profile


def quick_priority_keywords(priorities: list[str]) -> list[str]:
    keywords: list[str] = []
    for priority in priorities:
        keywords.extend(QUICK_PRIORITY_FEATURE_MAP.get(priority.lower(), []))
    return list({keyword.lower() for keyword in keywords})


def normalized_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip().lower() for item in value]
    return []
