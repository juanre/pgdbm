"""API Gateway for microservices."""

import os
import time
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from shared.database import SharedDatabaseManager, register_service
from shared.events import event_bus

from .routes import router

# Service configuration
SERVICE_NAME = os.getenv("SERVICE_NAME", "gateway")
SERVICE_PORT = int(os.getenv("SERVICE_PORT", "8000"))
SERVICE_URL = f"http://localhost:{SERVICE_PORT}"

# Track startup time
startup_time = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Initialize shared database
    shared_db = await SharedDatabaseManager.get_instance()

    # Run migrations
    await shared_db.run_migrations()

    # Initialize event bus
    await event_bus.initialize()

    # Register service
    await register_service(SERVICE_NAME, SERVICE_URL)

    yield

    # Cleanup
    await event_bus.close()
    await shared_db.close()


# Create FastAPI app
app = FastAPI(
    title="Microservices Gateway",
    description="API Gateway for microservices architecture example",
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
app.include_router(router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "service": SERVICE_NAME,
        "version": "1.0.0",
        "docs": "/docs",
        "services": [
            {"name": "user-service", "endpoint": "/api/users"},
            {"name": "order-service", "endpoint": "/api/orders"},
            {"name": "inventory-service", "endpoint": "/api/inventory"},
            {"name": "notification-service", "endpoint": "/api/notifications"},
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
        "timestamp": datetime.utcnow(),
    }


@app.get("/health/ready")
async def readiness_check():
    """Readiness check with database connectivity."""
    try:
        shared_db = await SharedDatabaseManager.get_instance()
        db = shared_db.get_manager()
        await db.execute("SELECT 1")

        return {"status": "ready", "database": "connected", "service": SERVICE_NAME}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "not ready", "error": str(e)})


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "service": SERVICE_NAME, "path": request.url.path},
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    print(f"Unhandled exception: {exc}")

    return JSONResponse(
        status_code=500, content={"error": "Internal server error", "service": SERVICE_NAME}
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("gateway.main:app", host="0.0.0.0", port=SERVICE_PORT, reload=True)
