"""Main FastAPI application."""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .api import health, todos
from .config import config
from .db import TodoDatabase
from .models import ErrorResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    app.state.db = TodoDatabase()
    await app.state.db.initialize()
    await app.state.db.apply_migrations()

    yield

    # Shutdown
    await app.state.db.close()


# Create FastAPI app
app = FastAPI(
    title="Todo API",
    description="A simple todo API demonstrating pgdbm usage",
    version="1.0.0",
    lifespan=lifespan,
)


# Exception handlers
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions."""
    request_id = str(uuid.uuid4())

    # Log the error (in production, use proper logging)
    print(f"[{request_id}] Unhandled exception: {exc}")

    return JSONResponse(
        status_code=500,
        content=ErrorResponse(
            error="Internal server error",
            detail=str(exc) if not config.is_production else None,
            request_id=request_id,
        ).model_dump(),
    )


# Include routers
app.include_router(health.router)
app.include_router(todos.router, prefix=config.api_prefix)


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "Todo API", "version": "1.0.0", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=config.app_env == "development")
