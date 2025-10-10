"""Base database wrapper for row-level multi-tenant SaaS.

This example demonstrates row-level multi-tenancy where all tenants share
the same tables and are isolated by a tenant_id column in each row.
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from pgdbm import AsyncDatabaseManager, AsyncDBError, DatabaseConfig


class BaseDatabase:
    """Base database wrapper with multi-tenant support."""

    def __init__(self, db_manager: Optional[AsyncDatabaseManager] = None):
        """Initialize with optional external database manager."""
        self._external_db = db_manager is not None
        self.db = db_manager
        self._migrations_path = Path(__file__).parent.parent.parent / "migrations"

    async def initialize(self, config: DatabaseConfig) -> None:
        """Initialize database connection if not using external manager."""
        if not self._external_db:
            self.db = AsyncDatabaseManager(config)
            await self.db.connect()

    async def close(self) -> None:
        """Close database connection if we manage it."""
        if self.db and not self._external_db:
            await self.db.disconnect()

    async def execute(self, query: str, *args) -> Any:
        """Execute query."""
        if not self.db:
            raise AsyncDBError("Database not initialized")

        return await self.db.execute(query, *args)

    async def fetch_one(self, query: str, *args) -> Optional[dict[str, Any]]:
        """Fetch one row."""
        if not self.db:
            raise AsyncDBError("Database not initialized")

        return await self.db.fetch_one(query, *args)

    async def fetch_all(self, query: str, *args) -> list[dict[str, Any]]:
        """Fetch all rows."""
        if not self.db:
            raise AsyncDBError("Database not initialized")

        return await self.db.fetch_all(query, *args)

    async def execute_many(self, query: str, args_list: list[tuple]) -> None:
        """Execute query multiple times with different arguments."""
        if not self.db:
            raise AsyncDBError("Database not initialized")

        return await self.db.executemany(query, args_list)

    @asynccontextmanager
    async def transaction(self):
        """Transaction context manager with automatic template substitution."""
        if not self.db:
            raise AsyncDBError("Database not initialized")

        async with self.db.transaction() as tx:
            yield tx

    # Row-level multi-tenancy doesn't need schema management methods
    # All tenants share the same tables with tenant_id isolation
