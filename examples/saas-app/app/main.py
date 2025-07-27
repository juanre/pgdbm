"""Main FastAPI application for multi-tenant SaaS."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from pgdbm import AsyncDatabaseManager, DatabaseConfig

from .api import admin, auth, projects, tenants
from .config import config
from .db.admin import AdminDatabase
from .middleware.tenant import api_key_middleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Initialize shared database connection pool
    db_config = DatabaseConfig(connection_string=config.database_url)
    db_manager = AsyncDatabaseManager(db_config)
    await db_manager.connect()

    # Create admin database wrapper
    admin_db = AdminDatabase(db_manager)

    # Store in app state
    app.state.db = db_manager
    app.state.admin_db = admin_db

    # Run public schema migrations if needed
    if config.app_env != "testing":
        migration_manager = await admin_db.get_migration_manager()
        await migration_manager.ensure_migrations_table()
        pending = await migration_manager.get_pending_migrations()

        if pending:
            print(f"Applying {len(pending)} pending migration(s)...")
            for migration in pending:
                await migration_manager.apply_migration(migration)
            print("✓ Migrations applied successfully")

    yield

    # Cleanup
    await db_manager.disconnect()


# Create FastAPI app
app = FastAPI(
    title="Multi-Tenant SaaS Example",
    description="Example SaaS application with schema-based multi-tenancy using pgdbm",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Add API key authentication middleware
@app.middleware("http")
async def add_api_key_auth(request: Request, call_next):
    """Add API key authentication to requests."""
    return await api_key_middleware(request, call_next)


# Include routers
app.include_router(auth.router)
app.include_router(tenants.router)
app.include_router(projects.router)
app.include_router(admin.router)


@app.get("/")
async def root():
    """Root endpoint."""
    return {"name": "Multi-Tenant SaaS Example", "version": "1.0.0", "docs": "/docs"}


@app.get("/health")
async def health_check():
    """Basic health check."""
    return {"status": "healthy"}


@app.get("/health/ready")
async def readiness_check(request: Request):
    """Readiness check with database connectivity."""
    try:
        db = request.app.state.admin_db
        await db.execute("SELECT 1")
        return {"status": "ready", "database": "connected"}
    except Exception as e:
        return JSONResponse(status_code=503, content={"status": "not ready", "error": str(e)})


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler."""
    # Log the error (in production, use proper logging)
    print(f"Unhandled exception: {exc}")

    # Don't expose internal errors in production
    if config.is_production:
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return JSONResponse(status_code=500, content={"detail": str(exc)})


if __name__ == "__main__":
    import uvicorn

    # Run with: python -m app.main
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
