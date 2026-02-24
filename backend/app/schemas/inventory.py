from pydantic import BaseModel


class InventorySearchResponse(BaseModel):
    vin: str
    year: int
    make: str
    model: str
    body_type: str | None
    price_asking: float
    available: bool
