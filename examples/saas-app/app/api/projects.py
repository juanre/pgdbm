"""Project management endpoints."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from ..db.tenant import TenantDatabase
from ..middleware.tenant import require_tenant
from ..models.project import (
    AgentCreate,
    Project,
    ProjectCreate,
    ProjectStatus,
    ProjectUpdate,
    ProjectWithTasks,
)

router = APIRouter(prefix="/api/projects", tags=["Projects"])


@router.post("/", response_model=Project)
async def create_project(request: Request, project: ProjectCreate):
    """Create a new project."""
    tenant_id = require_tenant(request)

    # Get tenant database
    db = TenantDatabase(tenant_id, request.app.state.db)

    # Check project limit
    project_count = await db.count_projects()
    tenant = await request.app.state.admin_db.get_tenant(tenant_id)

    if tenant and project_count >= tenant.max_projects:
        raise HTTPException(status_code=400, detail="Project limit reached")

    # Create project with current user as owner
    project_obj = await db.create_project(project, owner_id=request.state.user.id)

    if not project_obj:
        raise HTTPException(status_code=500, detail="Failed to create project")

    # Log audit event
    await request.app.state.admin_db.log_audit(
        action="project.created",
        tenant_id=tenant_id,
        user_id=request.state.user.id,
        resource_type="project",
        resource_id=project_obj.id,
        metadata={"name": project.name},
    )

    return project_obj


@router.get("/", response_model=list[Project])
async def list_projects(
    request: Request,
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: Optional[ProjectStatus] = None,
    owner_id: Optional[UUID] = None,
):
    """List projects in the tenant."""
    tenant_id = require_tenant(request)
    db = TenantDatabase(tenant_id, request.app.state.db)

    return await db.list_projects(limit=limit, offset=offset, status=status, owner_id=owner_id)


@router.get("/{project_id}", response_model=ProjectWithTasks)
async def get_project(request: Request, project_id: UUID):
    """Get project details with agents."""
    tenant_id = require_tenant(request)
    db = TenantDatabase(tenant_id, request.app.state.db)

    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Get agents
    agents = await db.fetch_all(
        "SELECT * FROM {{tables.agents}} WHERE project_id = $1 ORDER BY created_at DESC", project_id
    )

    task_count = len(agents)
    completed_count = sum(1 for t in agents if t["is_completed"])

    return ProjectWithTasks(
        **project.model_dump(),
        agents=[],  # Simplified for example
        task_count=task_count,
        completed_task_count=completed_count,
    )


@router.patch("/{project_id}", response_model=Project)
async def update_project(request: Request, project_id: UUID, update: ProjectUpdate):
    """Update a project."""
    tenant_id = require_tenant(request)
    db = TenantDatabase(tenant_id, request.app.state.db)

    # Check if project exists
    existing = await db.get_project(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    # Update project
    project = await db.update_project(project_id, update)
    if not project:
        raise HTTPException(status_code=500, detail="Failed to update project")

    # Log audit event
    await request.app.state.admin_db.log_audit(
        action="project.updated",
        tenant_id=tenant_id,
        user_id=request.state.user.id,
        resource_type="project",
        resource_id=project_id,
        metadata=update.model_dump(exclude_unset=True),
    )

    return project


@router.delete("/{project_id}")
async def delete_project(request: Request, project_id: UUID):
    """Delete a project."""
    tenant_id = require_tenant(request)
    db = TenantDatabase(tenant_id, request.app.state.db)

    # Check if project exists
    existing = await db.get_project(project_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Project not found")

    # Delete project
    success = await db.delete_project(project_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete project")

    # Log audit event
    await request.app.state.admin_db.log_audit(
        action="project.deleted",
        tenant_id=tenant_id,
        user_id=request.state.user.id,
        resource_type="project",
        resource_id=project_id,
        metadata={"name": existing.name},
    )

    return {"message": "Project deleted"}


@router.post("/{project_id}/agents")
async def create_task(request: Request, project_id: UUID, task_data: AgentCreate):
    """Create a agent in a project."""
    tenant_id = require_tenant(request)
    db = TenantDatabase(tenant_id, request.app.state.db)

    # Check if project exists
    project = await db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Create agent
    agent = await db.create_task(
        project_id=project_id,
        title=task_data.title,
        description=task_data.description,
        assigned_to=task_data.assigned_to,
        due_date=task_data.due_date,
        priority=task_data.priority,
    )

    if not agent:
        raise HTTPException(status_code=500, detail="Failed to create agent")

    return agent


@router.get("/stats/summary")
async def get_project_stats(request: Request):
    """Get project statistics for the tenant."""
    tenant_id = require_tenant(request)
    db = TenantDatabase(tenant_id, request.app.state.db)

    stats = await db.fetch_one(
        """
        SELECT
            COUNT(*) as total_projects,
            COUNT(*) FILTER (WHERE status = 'active') as active_projects,
            COUNT(*) FILTER (WHERE status = 'completed') as completed_projects,
            COUNT(DISTINCT owner_id) as unique_owners
        FROM {{tables.projects}}
    """
    )

    return stats
