"""User service for authentication and user management."""

import os
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.database import SharedDatabaseManager, register_service
from shared.events import event_bus

from .api import router
from .db import UserDatabase

# Service configuration
SERVICE_NAME = os.getenv("SERVICE_NAME", "user-service")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8001"))
SERVICE_URL = f"http://localhost:{SERVICE_PORT}"

# Track startup time
startup_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Initialize shared database
    await SharedDatabaseManager.get_instance()

    # Initialize service database
    app.state.db = UserDatabase()
    await app.state.db.initialize()

    # Initialize event bus
    await event_bus.initialize()

    # Register service
    await register_service(SERVICE_NAME, SERVICE_URL)

    yield

    # Cleanup
    await event_bus.close()


# Create FastAPI app
app = FastAPI(
    title="User Service",
    description="User authentication and management service",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routes
app.include_router(router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": SERVICE_NAME,
        "version": "1.0.0",
        "endpoints": [
            "/api/users/register",
            "/api/users/login",
            "/api/users/me",
            "/api/users/{user_id}",
        ],
    }


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    uptime = time.time() - startup_time

    return {
        "service_name": SERVICE_NAME,
        "status": "healthy",
        "version": "1.0.0",
        "uptime_seconds": round(uptime, 2),
        "database": "connected",
        "timestamp": datetime.utcnow(),
    }


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    print(f"Unhandled exception in {SERVICE_NAME}: {exc}")

    return JSONResponse(
        status_code=500, content={"error": "Internal server error", "service": SERVICE_NAME}
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("services.user.main:app", host="0.0.0.0", port=SERVICE_PORT, reload=True)
