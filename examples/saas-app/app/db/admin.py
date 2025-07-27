"""Admin database operations for cross-tenant access."""

import json
from datetime import date
from typing import Any, Optional
from uuid import UUID

from ..models.tenant import Tenant, TenantCreate, TenantPlan, TenantStatus, TenantUpdate
from .base import BaseDatabase


class AdminDatabase(BaseDatabase):
    """Database wrapper for admin operations across all tenants."""

    def __init__(self, db_manager: Optional[Any] = None):
        """Initialize admin database for cross-tenant operations."""
        super().__init__(db_manager=db_manager)

    def _parse_tenant_result(self, result: dict[str, Any]) -> Tenant:
        """Parse tenant result, converting JSON strings to dicts."""
        if isinstance(result.get("metadata"), str):
            result_dict = dict(result)
            result_dict["metadata"] = json.loads(result_dict["metadata"])
            return Tenant(**result_dict)
        return Tenant(**result)

    async def get_migration_manager(self) -> Any:
        """Get migration manager for public schema migrations."""
        from pgdbm import AsyncMigrationManager

        return AsyncMigrationManager(
            db_manager=self.db,
            migrations_path=str(self._migrations_path),
            migrations_table="schema_migrations",
        )

    # Tenant management
    async def create_tenant(self, tenant: TenantCreate) -> Tenant:
        """Create a new tenant."""
        # Create tenant record
        query = """
            INSERT INTO tenants (
                slug, name, email, plan,
                max_projects, max_users, metadata
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
        """

        result = await self.fetch_one(
            query,
            tenant.slug,
            tenant.name,
            tenant.email,
            tenant.plan.value if tenant.plan else TenantPlan.FREE.value,
            tenant.max_projects or 10,
            tenant.max_users or 5,
            json.dumps(tenant.metadata or {}),
        )

        if result:
            return self._parse_tenant_result(result)
        return None

    async def get_tenant(self, tenant_id: UUID) -> Optional[Tenant]:
        """Get tenant by ID."""
        query = "SELECT * FROM tenants WHERE id = $1"
        result = await self.fetch_one(query, tenant_id)
        return self._parse_tenant_result(result) if result else None

    async def get_tenant_by_slug(self, slug: str) -> Optional[Tenant]:
        """Get tenant by slug."""
        query = "SELECT * FROM tenants WHERE slug = $1"
        result = await self.fetch_one(query, slug)
        return self._parse_tenant_result(result) if result else None

    async def list_tenants(
        self,
        limit: int = 10,
        offset: int = 0,
        status: Optional[TenantStatus] = None,
        plan: Optional[TenantPlan] = None,
    ) -> list[Tenant]:
        """List tenants with filters."""
        query = "SELECT * FROM tenants WHERE 1=1"
        params = []
        param_count = 0

        if status:
            param_count += 1
            query += f" AND status = ${param_count}"
            params.append(status.value)

        if plan:
            param_count += 1
            query += f" AND plan = ${param_count}"
            params.append(plan.value)

        query += " ORDER BY created_at DESC"

        param_count += 1
        query += f" LIMIT ${param_count}"
        params.append(limit)

        param_count += 1
        query += f" OFFSET ${param_count}"
        params.append(offset)

        results = await self.fetch_all(query, *params)
        return [self._parse_tenant_result(row) for row in results]

    async def update_tenant(self, tenant_id: UUID, update: TenantUpdate) -> Optional[Tenant]:
        """Update tenant."""
        fields = []
        params = []
        param_count = 0

        update_dict = update.model_dump(exclude_unset=True)

        for field, value in update_dict.items():
            if value is not None:
                param_count += 1
                fields.append(f"{field} = ${param_count}")
                params.append(value.value if hasattr(value, "value") else value)

        if not fields:
            return await self.get_tenant(tenant_id)

        param_count += 1
        params.append(tenant_id)

        query = f"""
            UPDATE tenants
            SET {', '.join(fields)}
            WHERE id = ${param_count}
            RETURNING *
        """

        result = await self.fetch_one(query, *params)
        return self._parse_tenant_result(result) if result else None

    async def suspend_tenant(self, tenant_id: UUID, reason: Optional[str] = None) -> bool:
        """Suspend a tenant."""
        query = """
            UPDATE tenants
            SET status = 'suspended', suspended_at = NOW()
            WHERE id = $1
        """
        await self.execute(query, tenant_id)

        # Log the action
        await self.log_audit(
            tenant_id=tenant_id,
            action="tenant.suspended",
            metadata=json.dumps({"reason": reason} if reason else {}),
        )

        return True

    async def delete_tenant(self, tenant_id: UUID) -> bool:
        """Delete tenant and all their data."""
        tenant = await self.get_tenant(tenant_id)
        if not tenant:
            return False

        # Delete tenant record (cascades to all related data via FK constraints)
        await self.execute("DELETE FROM tenants WHERE id = $1", tenant_id)

        return True

    # User management
    async def create_user(
        self,
        email: str,
        password_hash: str,
        tenant_id: Optional[UUID] = None,
        is_admin: bool = False,
        display_name: Optional[str] = None,
        role: str = "member",
    ) -> dict[str, Any]:
        """Create a user."""
        query = """
            INSERT INTO users (email, password_hash, tenant_id, is_admin, display_name, role)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *
        """

        return await self.fetch_one(
            query,
            email,
            password_hash,
            tenant_id,
            is_admin,
            display_name or email.split("@")[0],
            role,
        )

    async def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        """Get user by email."""
        query = "SELECT * FROM users WHERE email = $1"
        return await self.fetch_one(query, email)

    async def update_last_login(self, user_id: UUID) -> None:
        """Update user's last login timestamp."""
        await self.execute("UPDATE users SET last_login_at = NOW() WHERE id = $1", user_id)

    # Usage tracking
    async def track_usage(
        self,
        tenant_id: UUID,
        metric_name: str,
        metric_value: int,
        period_start: date,
        period_end: date,
    ) -> None:
        """Track tenant usage metrics."""
        query = """
            INSERT INTO tenant_usage (tenant_id, metric_name, metric_value, period_start, period_end)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (tenant_id, metric_name, period_start, period_end)
            DO UPDATE SET metric_value = tenant_usage.metric_value + EXCLUDED.metric_value
        """

        await self.execute(query, tenant_id, metric_name, metric_value, period_start, period_end)

    async def get_tenant_usage(
        self, tenant_id: UUID, period_start: date, period_end: date
    ) -> list[dict[str, Any]]:
        """Get tenant usage for a period."""
        query = """
            SELECT metric_name, SUM(metric_value) as total_value
            FROM tenant_usage
            WHERE tenant_id = $1 AND period_start >= $2 AND period_end <= $3
            GROUP BY metric_name
        """

        return await self.fetch_all(query, tenant_id, period_start, period_end)

    # Cross-tenant queries
    async def get_all_tenants_stats(self) -> list[dict[str, Any]]:
        """Get statistics across all tenants."""
        query = """
            SELECT
                t.id,
                t.name,
                t.plan,
                t.status,
                COUNT(DISTINCT u.id) as user_count,
                t.created_at
            FROM tenants t
            LEFT JOIN users u ON u.tenant_id = t.id
            GROUP BY t.id
            ORDER BY t.created_at DESC
        """

        return await self.fetch_all(query)

    async def execute_cross_tenant(
        self, query_template: str, tenant_ids: Optional[list[UUID]] = None
    ) -> list[dict[str, Any]]:
        """Execute a query across multiple tenants using row-level filtering."""
        # For row-level tenancy, we don't need to iterate through tenants
        # We can get all data in one query and add tenant info

        if tenant_ids:
            # Filter specific tenants
            placeholders = ",".join(f"${i+1}" for i in range(len(tenant_ids)))
            query = query_template.replace("WHERE", f"WHERE tenant_id IN ({placeholders}) AND")
            if "WHERE" not in query_template:
                query = query_template.replace("FROM {{tables.", "FROM {tables.")
                query = query.replace("}}", f"}} WHERE tenant_id IN ({placeholders})")
            results = await self.fetch_all(query, *tenant_ids)
        else:
            # Get all tenant data
            results = await self.fetch_all(query_template)

        # Add tenant names to results
        tenant_cache = {}
        for row in results:
            if "tenant_id" in row and row["tenant_id"] not in tenant_cache:
                tenant = await self.get_tenant(row["tenant_id"])
                if tenant:
                    tenant_cache[row["tenant_id"]] = tenant.name

            if "tenant_id" in row and row["tenant_id"] in tenant_cache:
                row["_tenant_id"] = row["tenant_id"]
                row["_tenant_name"] = tenant_cache[row["tenant_id"]]

        return results

    # Audit logging
    async def log_audit(
        self,
        action: str,
        tenant_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[UUID] = None,
        metadata: Optional[dict[str, Any]] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        """Log an audit event."""
        query = """
            INSERT INTO audit_log (
                tenant_id, user_id, action, resource_type, resource_id,
                metadata, ip_address, user_agent
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7::inet, $8)
        """

        await self.execute(
            query,
            tenant_id,
            user_id,
            action,
            resource_type,
            resource_id,
            json.dumps(metadata or {}),
            ip_address,
            user_agent,
        )

    async def get_audit_log(
        self, tenant_id: Optional[UUID] = None, user_id: Optional[UUID] = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """Get audit log entries."""
        query = "SELECT * FROM audit_log WHERE 1=1"
        params = []
        param_count = 0

        if tenant_id:
            param_count += 1
            query += f" AND tenant_id = ${param_count}"
            params.append(tenant_id)

        if user_id:
            param_count += 1
            query += f" AND user_id = ${param_count}"
            params.append(user_id)

        query += " ORDER BY created_at DESC"

        param_count += 1
        query += f" LIMIT ${param_count}"
        params.append(limit)

        return await self.fetch_all(query, *params)


# CLI handler when run as module
if __name__ == "__main__":
    import asyncio
    import sys

    from pgdbm import AsyncDatabaseManager, DatabaseConfig

    from ..config import config

    async def run_migrate_public():
        """Run public schema migrations from CLI."""
        print("Running public schema migrations...")

        # Create database config
        db_config = DatabaseConfig(
            connection_string=config.database_url,
            min_connections=config.admin_pool_min,
            max_connections=config.admin_pool_max,
        )

        # Create database manager
        db_manager = AsyncDatabaseManager(db_config)

        try:
            await db_manager.connect()

            # Create admin database instance
            admin_db = AdminDatabase(db_manager)

            # Get migration manager
            migration_manager = await admin_db.get_migration_manager()

            # Create migrations table if needed
            await migration_manager.ensure_migrations_table()

            # Check for pending migrations
            pending = await migration_manager.get_pending_migrations()

            if not pending:
                print("✓ No pending migrations")
                return

            print(f"Found {len(pending)} pending migration(s):")
            for migration in pending:
                print(f"  - {migration.filename}")

            # Apply pending migrations
            for migration in pending:
                print(f"Applying {migration.filename}...")
                await migration_manager.apply_migration(migration)
                print("  ✓ Applied successfully")

            print("\n✓ All migrations completed successfully")

        except Exception as e:
            print(f"✗ Migration failed: {e}")
            sys.exit(1)
        finally:
            await db_manager.disconnect()

    if len(sys.argv) > 1 and sys.argv[1] == "migrate_public":
        asyncio.run(run_migrate_public())
    else:
        print("Usage: python -m app.db.admin migrate_public")
