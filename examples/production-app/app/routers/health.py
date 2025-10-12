"""Health check endpoints for monitoring."""

from fastapi import APIRouter, Response

from app.database import db_infrastructure

router = APIRouter(prefix="/health")


@router.get("")
async def health():
    """Basic health check."""
    return {"status": "healthy"}


@router.get("/ready")
async def readiness():
    """
    Readiness probe - checks if the application is ready to serve traffic.

    Returns 503 if any database connection fails.
    """
    health_status = await db_infrastructure.health_check()

    all_healthy = all(health_status.values())

    if not all_healthy:
        return Response(
            content={
                "status": "unhealthy",
                "services": health_status,
            },
            status_code=503,
        )

    return {
        "status": "ready",
        "services": health_status,
    }


@router.get("/live")
async def liveness():
    """
    Liveness probe - checks if the application is alive.

    This is a simple check that the application is running.
    Database failures don't affect liveness.
    """
    return {"status": "alive"}


@router.get("/metrics")
async def metrics():
    """
    Get application metrics including connection pool stats.

    In production, you'd typically use Prometheus metrics instead.
    """
    pool_stats = db_infrastructure.get_pool_stats()

    return {
        "pool": pool_stats,
        "services": list(db_infrastructure.managers.keys()),
    }
