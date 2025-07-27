"""Tenant context middleware."""

from fastapi import Request
from fastapi.responses import JSONResponse

from ..models.user import User


async def api_key_middleware(request: Request, call_next):
    """Middleware to set user context from API key."""
    # Skip for public endpoints
    public_paths = (
        "/docs",
        "/openapi.json",
        "/health",
        "/api/auth/register",
        "/api/auth/login",
        "/api/tenants/signup",
    )
    if request.url.path.startswith(public_paths):
        return await call_next(request)

    # Get API key from header
    api_key = request.headers.get("x-api-key")
    if not api_key:
        # For protected endpoints, require auth
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=401, content={"detail": "API key required"})
        return await call_next(request)

    # Validate API key
    db = request.app.state.admin_db
    user_dict = await db.fetch_one(
        "SELECT * FROM users WHERE api_key = $1 AND is_active = TRUE", api_key
    )

    if not user_dict:
        if request.url.path.startswith("/api/"):
            return JSONResponse(status_code=401, content={"detail": "Invalid API key"})
        return await call_next(request)

    # Set request state
    request.state.user = User(**user_dict)
    request.state.tenant_id = user_dict["tenant_id"]
    request.state.is_admin = user_dict["is_admin"]

    response = await call_next(request)
    return response


def require_tenant(request: Request) -> str:
    """Require tenant context to be set."""
    from fastapi import HTTPException

    if not hasattr(request.state, "tenant_id") or not request.state.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return request.state.tenant_id


def require_admin(request: Request) -> User:
    """Require admin user."""
    from fastapi import HTTPException

    if not hasattr(request.state, "is_admin") or not request.state.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    return request.state.user
