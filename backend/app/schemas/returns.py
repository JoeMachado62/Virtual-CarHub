from pydantic import BaseModel, Field


class InitiateReturnRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)
    buyer_transport_responsibility: bool = True


class ConfirmReceiptRequest(BaseModel):
    damage_deduction: float = 0.0


class RefundRequest(BaseModel):
    restocking_fee: float = 0.0
    damage_deduction: float = 0.0
