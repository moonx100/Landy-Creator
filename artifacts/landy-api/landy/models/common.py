"""Common Pydantic models shared across the API."""
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str = "ok"
