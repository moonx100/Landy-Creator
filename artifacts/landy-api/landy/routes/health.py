"""Health check endpoint.

GET /api/healthz — returns {"status": "ok"}.
Used by docker-compose healthchecks and load balancers.
Does not require authentication; does not touch the database.
"""
from fastapi import APIRouter
from landy.models.common import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=HealthResponse)
def health_check() -> HealthResponse:
    return HealthResponse(status="ok")
