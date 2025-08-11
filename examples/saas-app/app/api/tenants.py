"""Tenant management endpoints."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request
from passlib.context import CryptContext

from ..db.tenant import TenantDatabase
from ..middleware.tenant import require_admin
from ..models.tenant import (
    Tenant,
    TenantCreate,
    TenantPlan,
    TenantSignup,
    TenantStatus,
    TenantUpdate,
    TenantWithUsage,
)
from ..models.user import UserWithApiKey
from .auth import generate_api_key, get_password_hash

router = APIRouter(prefix="/api/tenants", tags=["Tenants"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


@router.post("/signup", response_model=UserWithApiKey)
async def signup_tenant(request: Request, signup_data: TenantSignup):
    """Sign up a new tenant with admin user."""
    db = request.app.state.admin_db

    # Check if slug is taken
    existing = await db.get_tenant_by_slug(signup_data.slug)
    if existing:
        raise HTTPException(status_code=400, detail="Tenant slug already taken")

    # Check if email is taken
    existing_user = await db.get_user_by_email(signup_data.email)
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create tenant (extract TenantCreate fields)
    tenant_data = TenantCreate(
        name=signup_data.name,
        email=signup_data.email,
        slug=signup_data.slug,
        plan=signup_data.plan,
        max_projects=signup_data.max_projects,
        max_users=signup_data.max_users,
        metadata=signup_data.metadata,
    )
    tenant = await db.create_tenant(tenant_data)
    if not tenant:
        raise HTTPException(status_code=500, detail="Failed to create tenant")

    # Create admin user for the tenant
    password_hash = get_password_hash(signup_data.admin_password)
    user_dict = await db.create_user(
        email=signup_data.email,
        password_hash=password_hash,
        tenant_id=tenant.id,
        is_admin=False,  # Not a global admin
    )

    if not user_dict:
        # Rollback tenant creation
        await db.delete_tenant(tenant.id)
        raise HTTPException(status_code=500, detail="Failed to create user")

    # Generate API key
    api_key = generate_api_key()
    await db.execute("UPDATE users SET api_key = $1 WHERE id = $2", api_key, user_dict["id"])

    # Log audit event
    await db.log_audit(
        action="tenant.created",
        tenant_id=tenant.id,
        user_id=user_dict["id"],
        metadata={"tenant_slug": tenant.slug, "plan": tenant.plan.value},
    )

    user_dict["api_key"] = api_key
    return UserWithApiKey(**user_dict)


@router.get("/", response_model=list[Tenant])
async def list_tenants(
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[TenantStatus] = None,
    plan: Optional[TenantPlan] = None,
):
    """List all tenants (admin only)."""
    require_admin(request)
    db = request.app.state.admin_db

    return await db.list_tenants(limit=limit, offset=offset, status=status, plan=plan)


@router.get("/current", response_model=TenantWithUsage)
async def get_current_tenant(request: Request):
    """Get current tenant information."""
    if not hasattr(request.state, "tenant_id") or not request.state.tenant_id:
        raise HTTPException(status_code=403, detail="Not in tenant context")

    db = request.app.state.admin_db
    tenant = await db.get_tenant(request.state.tenant_id)

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Get usage stats
    tenant_db = TenantDatabase(request.state.tenant_id, db)
    stats = await tenant_db.get_usage_stats()

    return TenantWithUsage(
        **tenant.model_dump(),
        user_count=stats["team_members"]["total"],
        project_count=stats["projects"]["total"],
        task_count=stats["agents"]["total"],
    )


@router.get("/{tenant_id}", response_model=TenantWithUsage)
async def get_tenant(request: Request, tenant_id: UUID):
    """Get tenant by ID (admin only)."""
    require_admin(request)
    db = request.app.state.admin_db

    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Get usage stats
    tenant_db = TenantDatabase(str(tenant_id), db)
    stats = await tenant_db.get_usage_stats()

    return TenantWithUsage(
        **tenant.model_dump(),
        user_count=stats["team_members"]["total"],
        project_count=stats["projects"]["total"],
        task_count=stats["agents"]["total"],
    )


@router.patch("/{tenant_id}", response_model=Tenant)
async def update_tenant(request: Request, tenant_id: UUID, update: TenantUpdate):
    """Update tenant (admin only)."""
    require_admin(request)
    db = request.app.state.admin_db

    tenant = await db.update_tenant(tenant_id, update)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    # Log audit event
    await db.log_audit(
        action="tenant.updated",
        tenant_id=tenant_id,
        user_id=request.state.user.id,
        metadata=update.model_dump(exclude_unset=True),
    )

    return tenant


@router.post("/{tenant_id}/suspend")
async def suspend_tenant(request: Request, tenant_id: UUID, reason: Optional[str] = None):
    """Suspend a tenant (admin only)."""
    require_admin(request)
    db = request.app.state.admin_db

    success = await db.suspend_tenant(tenant_id, reason)
    if not success:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {"message": "Tenant suspended"}


@router.delete("/{tenant_id}")
async def delete_tenant(request: Request, tenant_id: UUID):
    """Delete a tenant and all data (admin only)."""
    require_admin(request)
    db = request.app.state.admin_db

    success = await db.delete_tenant(tenant_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return {"message": "Tenant deleted"}


@router.get("/{tenant_id}/audit", response_model=list[dict])
async def get_tenant_audit_log(
    request: Request, tenant_id: UUID, limit: int = Query(100, ge=1, le=1000)
):
    """Get tenant audit log (admin only)."""
    require_admin(request)
    db = request.app.state.admin_db

    return await db.get_audit_log(tenant_id=tenant_id, limit=limit)
