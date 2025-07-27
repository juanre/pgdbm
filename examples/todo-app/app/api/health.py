"""Health check endpoints."""

from fastapi import APIRouter, Request, Response

from ..models import HealthStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthStatus)
async def health_check() -> HealthStatus:
    """Basic health check."""
    return HealthStatus(status="healthy", database="unknown")


@router.get("/health/ready", response_model=HealthStatus)
async def readiness_check(request: Request, response: Response) -> HealthStatus:
    """Readiness check including database connectivity."""
    db = request.app.state.db

    health = await db.health_check()

    if health["status"] != "healthy":
        response.status_code = 503

    return HealthStatus(**health)
