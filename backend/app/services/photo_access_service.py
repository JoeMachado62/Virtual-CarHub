from __future__ import annotations

from datetime import UTC, datetime

from app.core.constants import FundingState
from app.models.entities import Deal, User

PROTECTED_PHOTO_ELIGIBLE_FUNDING_STATES = {
    FundingState.PRE_APPROVED,
    FundingState.TERMS_ACCEPTED,
    FundingState.FINAL_APPROVAL_PENDING,
    FundingState.FULLY_FUNDED,
    FundingState.CASH_BUYER,
}


def can_view_protected_vehicle_photos(
    *,
    user: User | None,
    deal: Deal | None = None,
) -> bool:
    if user is None or not user.is_active:
        return False

    if user.is_preapproved:
        if user.preapproved_until and user.preapproved_until < datetime.now(UTC):
            return False
        return True

    if deal and deal.funding_state in PROTECTED_PHOTO_ELIGIBLE_FUNDING_STATES:
        return True

    return False


def protected_photo_access_message(
    *,
    user: User | None,
    deal: Deal | None = None,
) -> str:
    if user is None:
        return "Sign in and complete buyer pre-qualification to unlock actual vehicle photos."
    if can_view_protected_vehicle_photos(user=user, deal=deal):
        return "Your buyer account is cleared to view actual vehicle photos."
    return "Actual vehicle photos are available after buyer pre-qualification is completed."
