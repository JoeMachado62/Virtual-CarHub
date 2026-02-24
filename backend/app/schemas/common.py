from typing import Any

from pydantic import BaseModel


class ApiError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = {}


class Envelope(BaseModel):
    status: str
    data: Any | None = None
    error: ApiError | None = None
