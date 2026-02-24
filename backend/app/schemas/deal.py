from datetime import datetime

from pydantic import BaseModel

from app.core.constants import DealState, FundingState


class DealResponse(BaseModel):
    id: str
    stage: DealState
    funding_state: FundingState
    assigned_agent: str | None
    human_checkpoint_required: bool
    selected_vin: str | None
    delivered_at: datetime | None
    closed_at: datetime | None


class OverrideStateRequest(BaseModel):
    new_state: DealState
    reason: str
