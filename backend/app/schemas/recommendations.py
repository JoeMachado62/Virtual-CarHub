from pydantic import BaseModel


class RecommendationItem(BaseModel):
    vin: str
    year: int
    make: str
    model: str
    trim: str | None = None
    mileage: int | None = None
    price: float
    location: str | None = None
    match_score: float
    explainability: str
    market_retail: float | None = None
    target_acquisition: float
    estimated_otd: float
    danny_savings: float


class VehicleActionResponse(BaseModel):
    vin: str
    status: str
