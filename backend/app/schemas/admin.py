from pydantic import BaseModel


class DealSummary(BaseModel):
    id: str
    user_id: str
    stage: str
    funding_state: str
    human_checkpoint_required: bool
    selected_vin: str | None


class ExceptionSummary(BaseModel):
    deal_id: str | None
    event_type: str
    message: str
    created_at: str
