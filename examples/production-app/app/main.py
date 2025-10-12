"""Main FastAPI application with proper lifecycle management."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.database import db_infrastructure
from app.routers import analytics, health, orders, users

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.app_log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle.

    This ensures proper startup and shutdown of database connections.
    """
    logger.info(f"Starting {settings.app_name} in {settings.app_env} environment")

    try:
        # Initialize database infrastructure
        await db_infrastructure.initialize()
        logger.info("Database infrastructure initialized successfully")

        # Store reference in app state (optional, we use singleton)
        app.state.db_infrastructure = db_infrastructure

        yield

    finally:
        # Cleanup on shutdown
        logger.info("Shutting down application")
        await db_infrastructure.close()
        logger.info("Database connections closed")


# Create FastAPI app with lifespan
app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    lifespan=lifespan,
    debug=settings.app_debug,
    docs_url="/docs" if not settings.is_production else None,
    redoc_url="/redoc" if not settings.is_production else None,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle uncaught exceptions."""
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    if settings.app_debug:
        return JSONResponse(
            status_code=500, content={"detail": str(exc), "type": type(exc).__name__}
        )
    else:
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(users.router, prefix="/api/v1", tags=["users"])
app.include_router(orders.router, prefix="/api/v1", tags=["orders"])
app.include_router(analytics.router, prefix="/api/v1", tags=["analytics"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "environment": settings.app_env,
        "docs": "/docs" if not settings.is_production else None,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.app_debug,
        log_level=settings.app_log_level,
    )
