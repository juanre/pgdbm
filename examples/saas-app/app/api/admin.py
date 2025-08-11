"""Admin API endpoints."""

from datetime import date, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Query, Request

from ..db.admin import AdminDatabase
from ..middleware.tenant import require_admin

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/stats/overview")
async def get_system_overview(request: Request):
    """Get system-wide statistics (admin only)."""
    require_admin(request)
    db: AdminDatabase = request.app.state.admin_db

    # Get tenant stats
    tenant_stats = await db.fetch_one(
        """
        SELECT
            COUNT(*) as total_tenants,
            COUNT(*) FILTER (WHERE status = 'active') as active_tenants,
            COUNT(*) FILTER (WHERE plan = 'free') as free_tenants,
            COUNT(*) FILTER (WHERE plan = 'starter') as starter_tenants,
            COUNT(*) FILTER (WHERE plan = 'pro') as pro_tenants,
            COUNT(*) FILTER (WHERE plan = 'enterprise') as enterprise_tenants
        FROM tenants
    """
    )

    # Get user stats
    user_stats = await db.fetch_one(
        """
        SELECT
            COUNT(*) as total_users,
            COUNT(*) FILTER (WHERE is_admin) as admin_users,
            COUNT(*) FILTER (WHERE last_login_at > NOW() - INTERVAL '30 days') as active_users
        FROM users
    """
    )

    # Get recent signups
    recent_signups = await db.fetch_one(
        """
        SELECT
            COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '7 days') as last_7_days,
            COUNT(*) FILTER (WHERE created_at > NOW() - INTERVAL '30 days') as last_30_days
        FROM tenants
    """
    )

    return {"tenants": tenant_stats, "users": user_stats, "recent_signups": recent_signups}


@router.get("/stats/cross-tenant")
async def get_cross_tenant_stats(request: Request):
    """Get statistics across all tenants (admin only)."""
    require_admin(request)
    db: AdminDatabase = request.app.state.admin_db

    # Get project counts across all tenants
    project_stats = await db.fetch_one(
        """
        SELECT
            COUNT(*) as project_count,
            COUNT(*) FILTER (WHERE status = 'active') as active_projects
        FROM {{tables.projects}}
    """
    )

    total_projects = project_stats["project_count"]
    total_active = project_stats["active_projects"]

    # Get agent counts across all tenants
    task_stats = await db.fetch_one(
        """
        SELECT
            COUNT(*) as task_count,
            COUNT(*) FILTER (WHERE is_completed) as completed_tasks
        FROM {{tables.agents}}
    """
    )

    total_tasks = task_stats["task_count"]
    total_completed = task_stats["completed_tasks"]

    return {
        "projects": {"total": total_projects, "active": total_active, "by_tenant": project_stats},
        "agents": {"total": total_tasks, "completed": total_completed, "by_tenant": task_stats},
    }


@router.get("/usage/trends")
async def get_usage_trends(request: Request, days: int = Query(30, ge=1, le=365)):
    """Get usage trends over time (admin only)."""
    require_admin(request)
    db: AdminDatabase = request.app.state.admin_db

    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    # Get daily tenant signups
    signup_trends = await db.fetch_all(
        """
        SELECT
            DATE(created_at) as date,
            COUNT(*) as signups
        FROM tenants
        WHERE created_at >= $1
        GROUP BY DATE(created_at)
        ORDER BY date
    """,
        start_date,
    )

    # Get usage metrics
    usage_trends = await db.fetch_all(
        """
        SELECT
            period_start as date,
            metric_name,
            SUM(metric_value) as total_value
        FROM tenant_usage
        WHERE period_start >= $1 AND period_end <= $2
        GROUP BY period_start, metric_name
        ORDER BY period_start, metric_name
    """,
        start_date,
        end_date,
    )

    return {"signups": signup_trends, "usage": usage_trends}


@router.get("/tenants/{tenant_id}/usage")
async def get_tenant_usage_details(
    request: Request,
    tenant_id: UUID,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
):
    """Get detailed usage for a specific tenant (admin only)."""
    require_admin(request)
    db: AdminDatabase = request.app.state.admin_db

    # Default to last 30 days
    if not end_date:
        end_date = date.today()
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # Get tenant
    tenant = await db.get_tenant(tenant_id)
    if not tenant:
        return {"error": "Tenant not found"}

    # Get usage metrics
    usage = await db.get_tenant_usage(tenant_id, start_date, end_date)

    # Get current stats from tenant schema
    from ..db.tenant import TenantDatabase

    tenant_db = TenantDatabase(str(tenant_id), db)
    current_stats = await tenant_db.get_usage_stats()

    return {
        "tenant": tenant,
        "current_stats": current_stats,
        "usage_metrics": usage,
        "period": {"start": start_date, "end": end_date},
    }


@router.post("/migrate-public")
async def migrate_public_schema(request: Request):
    """Run public schema migrations (admin only)."""
    require_admin(request)
    db: AdminDatabase = request.app.state.admin_db

    # Get migration manager
    migration_manager = await db.get_migration_manager()

    # Create migrations table if needed
    await migration_manager.ensure_migrations_table()

    # Apply pending migrations
    pending = await migration_manager.get_pending_migrations()
    applied_count = 0

    for migration in pending:
        await migration_manager.apply_migration(migration)
        applied_count += 1

    return {"message": f"Applied {applied_count} migration(s)", "migrations_applied": applied_count}


@router.get("/audit-log")
async def get_system_audit_log(
    request: Request,
    limit: int = Query(100, ge=1, le=1000),
    tenant_id: Optional[UUID] = None,
    user_id: Optional[UUID] = None,
):
    """Get system audit log (admin only)."""
    require_admin(request)
    db: AdminDatabase = request.app.state.admin_db

    return await db.get_audit_log(tenant_id=tenant_id, user_id=user_id, limit=limit)
