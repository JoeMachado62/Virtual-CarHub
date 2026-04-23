from pydantic import BaseModel, Field

from app.core.constants import ProfileTier


class QuickMatchRequest(BaseModel):
    body_types_included: list[str] = Field(default_factory=list)
    budget_min: float = 0
    budget_max: float = 100000
    year_min: int | None = None
    year_max: int | None = None
    mileage_min: int | None = None
    mileage_max: int | None = None
    top_3_priorities: list[str] = Field(default_factory=list, max_length=3)
    brands_included: list[str] = Field(default_factory=list)
    brands_excluded: list[str] = Field(default_factory=list)
    delivery_zip: str | None = None


class ProfileUpdateRequest(BaseModel):
    profile_tier: ProfileTier = ProfileTier.FULL
    bfv_json: dict = Field(default_factory=dict)
    intake_steps_complete: list[str] = Field(default_factory=list)
    hard_constraints: dict = Field(default_factory=dict)
    demographics: dict = Field(default_factory=dict)
    is_complete: bool = False


class BuyerProfileResponse(BaseModel):
    profile_tier: ProfileTier
    version: int
    bfv_json: dict
    intake_steps_complete: list[str]
    hard_constraints: dict
    demographics: dict
    is_complete: bool
