"""Tenant-specific database operations."""

import json
from datetime import date
from typing import Any, Optional
from uuid import UUID

from ..models.project import Project, ProjectCreate, ProjectStatus, ProjectUpdate
from .base import BaseDatabase


class TenantDatabase(BaseDatabase):
    """Database wrapper for tenant-specific operations."""

    def __init__(self, tenant_id: str, db_manager: Optional[Any] = None):
        """Initialize with tenant ID."""
        self.tenant_id = UUID(tenant_id) if isinstance(tenant_id, str) else tenant_id
        # Row-level tenancy - we filter by tenant_id, not schema
        super().__init__(db_manager=db_manager)

    def _parse_project_result(self, result: dict[str, Any]) -> Project:
        """Parse project result, converting JSON strings to dicts."""
        if isinstance(result.get("metadata"), str):
            result_dict = dict(result)
            result_dict["metadata"] = json.loads(result_dict["metadata"])
            return Project(**result_dict)
        return Project(**result)

    # Project operations
    async def create_project(self, project: ProjectCreate, owner_id: UUID) -> Optional[Project]:
        """Create a new project."""
        query = """
            INSERT INTO projects (tenant_id, name, description, status, owner_id, start_date, end_date, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING *
        """

        result = await self.fetch_one(
            query,
            self.tenant_id,
            project.name,
            project.description,
            project.status.value if project.status else ProjectStatus.PLANNING.value,
            owner_id,
            project.start_date,
            project.end_date,
            json.dumps(project.metadata or {}),
        )

        return self._parse_project_result(result) if result else None

    async def get_project(self, project_id: UUID) -> Optional[Project]:
        """Get a project by ID."""
        query = "SELECT * FROM projects WHERE id = $1 AND tenant_id = $2"
        result = await self.fetch_one(query, project_id, self.tenant_id)
        return self._parse_project_result(result) if result else None

    async def get_usage_stats(self) -> dict[str, Any]:
        """Get usage statistics for the tenant."""
        # Get project stats
        project_stats = await self.fetch_one(
            """
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN status = 'active' THEN 1 END) as active,
                COUNT(CASE WHEN status = 'completed' THEN 1 END) as completed
            FROM projects WHERE tenant_id = $1
        """,
            self.tenant_id,
        )

        # Get agent stats
        task_stats = await self.fetch_one(
            """
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN is_completed THEN 1 END) as completed
            FROM agents WHERE tenant_id = $1
        """,
            self.tenant_id,
        )

        # Get user stats
        user_stats = await self.fetch_one(
            """
            SELECT COUNT(*) as total
            FROM users WHERE tenant_id = $1
        """,
            self.tenant_id,
        )

        return {
            "projects": project_stats or {"total": 0, "active": 0, "completed": 0},
            "agents": task_stats or {"total": 0, "completed": 0},
            "team_members": {"total": user_stats["total"] if user_stats else 0},
        }

    async def list_projects(
        self,
        status: Optional[ProjectStatus] = None,
        owner_id: Optional[UUID] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Project]:
        """List projects with filtering."""
        conditions = ["tenant_id = $1"]
        params = [self.tenant_id]
        param_count = 2

        if status:
            conditions.append(f"status = ${param_count}")
            params.append(status.value)
            param_count += 1

        if owner_id:
            conditions.append(f"owner_id = ${param_count}")
            params.append(owner_id)
            param_count += 1

        query = f"""
            SELECT * FROM projects
            WHERE {' AND '.join(conditions)}
            ORDER BY created_at DESC
            LIMIT ${param_count} OFFSET ${param_count + 1}
        """

        params.extend([limit, offset])
        results = await self.fetch_all(query, *params)
        return [self._parse_project_result(r) for r in results]

    async def count_projects(self) -> int:
        """Count total projects for this tenant."""
        query = "SELECT COUNT(*) as count FROM projects WHERE tenant_id = $1"
        result = await self.fetch_one(query, self.tenant_id)
        return result["count"] if result else 0

    async def update_project(self, project_id: UUID, update: ProjectUpdate) -> Optional[Project]:
        """Update a project."""
        # Build dynamic update
        updates = []
        params = [project_id, self.tenant_id]
        param_count = 3

        if update.name is not None:
            updates.append(f"name = ${param_count}")
            params.append(update.name)
            param_count += 1

        if update.description is not None:
            updates.append(f"description = ${param_count}")
            params.append(update.description)
            param_count += 1

        if update.status is not None:
            updates.append(f"status = ${param_count}")
            params.append(update.status.value)
            param_count += 1

        if update.start_date is not None:
            updates.append(f"start_date = ${param_count}")
            params.append(update.start_date)
            param_count += 1

        if update.end_date is not None:
            updates.append(f"end_date = ${param_count}")
            params.append(update.end_date)
            param_count += 1

        if update.metadata is not None:
            updates.append(f"metadata = ${param_count}")
            params.append(json.dumps(update.metadata))
            param_count += 1

        if not updates:
            return await self.get_project(project_id)

        query = f"""
            UPDATE projects
            SET {', '.join(updates)}
            WHERE id = $1 AND tenant_id = $2
            RETURNING *
        """

        result = await self.fetch_one(query, *params)
        return self._parse_project_result(result) if result else None

    async def delete_project(self, project_id: UUID) -> bool:
        """Delete a project."""
        result = await self.execute(
            "DELETE FROM projects WHERE id = $1 AND tenant_id = $2", project_id, self.tenant_id
        )
        return "DELETE 1" in result

    # User operations
    async def get_tenant_users(self, limit: int = 100, offset: int = 0) -> list[dict[str, Any]]:
        """Get all users in the tenant."""
        query = """
            SELECT id, email, display_name, role, permissions, is_active,
                   created_at, last_login_at
            FROM users
            WHERE tenant_id = $1
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
        """
        return await self.fetch_all(query, self.tenant_id, limit, offset)

    async def get_user_by_id(self, user_id: UUID) -> Optional[dict[str, Any]]:
        """Get a user by ID within the tenant."""
        query = """
            SELECT id, email, display_name, role, permissions, is_active,
                   created_at, last_login_at
            FROM users
            WHERE id = $1 AND tenant_id = $2
        """
        return await self.fetch_one(query, user_id, self.tenant_id)

    async def update_user_role(self, user_id: UUID, role: str) -> Optional[dict[str, Any]]:
        """Update a user's role within the tenant."""
        query = """
            UPDATE users
            SET role = $3
            WHERE id = $1 AND tenant_id = $2
            RETURNING id, email, display_name, role, permissions, is_active
        """
        return await self.fetch_one(query, user_id, self.tenant_id, role)

    # Agent operations
    async def create_task(
        self,
        project_id: UUID,
        title: str,
        description: Optional[str] = None,
        assigned_to: Optional[UUID] = None,
        due_date: Optional[date] = None,
        priority: int = 0,
    ) -> dict[str, Any]:
        """Create a new agent."""
        query = """
            INSERT INTO agents (
                tenant_id, project_id, title, description,
                assigned_to, due_date, priority
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
        """

        return await self.fetch_one(
            query, self.tenant_id, project_id, title, description, assigned_to, due_date, priority
        )

    async def get_project_tasks(
        self,
        project_id: UUID,
        is_completed: Optional[bool] = None,
        assigned_to: Optional[UUID] = None,
    ) -> list[dict[str, Any]]:
        """Get agents for a project."""
        conditions = ["tenant_id = $1", "project_id = $2"]
        params = [self.tenant_id, project_id]
        param_count = 3

        if is_completed is not None:
            conditions.append(f"is_completed = ${param_count}")
            params.append(is_completed)
            param_count += 1

        if assigned_to:
            conditions.append(f"assigned_to = ${param_count}")
            params.append(assigned_to)
            param_count += 1

        query = f"""
            SELECT * FROM agents
            WHERE {' AND '.join(conditions)}
            ORDER BY priority DESC, created_at DESC
        """

        return await self.fetch_all(query, *params)

    # Statistics
    async def get_project_stats(self) -> dict[str, Any]:
        """Get project statistics for the tenant."""
        query = """
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'active') as active,
                COUNT(*) FILTER (WHERE status = 'completed') as completed,
                COUNT(*) FILTER (WHERE status = 'on_hold') as on_hold
            FROM projects
            WHERE tenant_id = $1
        """

        result = await self.fetch_one(query, self.tenant_id)
        return dict(result) if result else {"total": 0, "active": 0, "completed": 0, "on_hold": 0}

    async def get_user_stats(self) -> dict[str, Any]:
        """Get user statistics for the tenant."""
        query = """
            SELECT
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE is_active = true) as active,
                COUNT(*) FILTER (WHERE role = 'admin') as admins
            FROM users
            WHERE tenant_id = $1
        """

        result = await self.fetch_one(query, self.tenant_id)
        return dict(result) if result else {"total": 0, "active": 0, "admins": 0}
