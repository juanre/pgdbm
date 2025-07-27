"""Database wrapper for the todo application."""

import sys
from pathlib import Path
from typing import Any, Optional

from pgdbm import (
    AsyncDatabaseManager,
    AsyncMigrationManager,
    DatabaseConfig,
    MonitoredAsyncDatabaseManager,
)

from .config import config


class TodoNotFoundError(Exception):
    """Todo does not exist."""

    def __init__(self, todo_id: str):
        self.todo_id = todo_id
        super().__init__(f"Todo {todo_id} not found")


class TodoDatabase:
    """Database wrapper for todo operations."""

    def __init__(self, db_manager: Optional[AsyncDatabaseManager] = None):
        """
        Initialize database wrapper.

        Args:
            db_manager: Optional external database manager for testing
        """
        self._external_db = db_manager is not None
        self.db = db_manager

    @classmethod
    def from_manager(cls, db_manager: AsyncDatabaseManager) -> "TodoDatabase":
        """Create instance from existing database manager."""
        return cls(db_manager=db_manager)

    async def initialize(self) -> None:
        """Initialize database connection."""
        if self._external_db:
            return  # Using external connection

        db_config = DatabaseConfig(
            connection_string=config.database_url,
            schema=config.database_schema,
            min_connections=config.db_min_connections,
            max_connections=config.db_max_connections,
            command_timeout=60,
            server_settings={"jit": "off"},
        )

        if config.enable_monitoring:
            self.db = MonitoredAsyncDatabaseManager(db_config)
        else:
            self.db = AsyncDatabaseManager(db_config)

        await self.db.connect()

        # Register prepared statements
        self._register_prepared_statements()

    def _register_prepared_statements(self) -> None:
        """Register frequently used queries for performance."""
        self.db.add_prepared_statement(
            "get_todo_by_id", "SELECT * FROM {{tables.todos}} WHERE id = $1"
        )

        self.db.add_prepared_statement(
            "list_todos_paginated",
            """
            SELECT * FROM {{tables.todos}}
            WHERE ($1::boolean IS NULL OR completed = $1)
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
        )

    async def apply_migrations(self) -> None:
        """Apply database migrations."""
        migrations_path = Path(__file__).parent.parent / "migrations"
        migrations = AsyncMigrationManager(self.db, migrations_path=str(migrations_path))

        result = await migrations.apply_pending_migrations()

        if result["applied"]:
            print(f"Applied {len(result['applied'])} migrations:")
            for m in result["applied"]:
                print(f"  - {m['filename']}")

    async def close(self) -> None:
        """Close database connection if we own it."""
        if self.db and not self._external_db:
            await self.db.disconnect()

    # Todo operations

    async def create_todo(self, title: str, description: Optional[str] = None) -> dict[str, Any]:
        """Create a new todo."""
        todo_id = await self.db.execute_and_return_id(
            """
            INSERT INTO {{tables.todos}} (title, description)
            VALUES ($1, $2)
            """,
            title,
            description,
        )

        return await self.get_todo(str(todo_id))

    async def get_todo(self, todo_id: str) -> dict[str, Any]:
        """Get a todo by ID."""
        todo = await self.db.fetch_one("SELECT * FROM {{tables.todos}} WHERE id = $1", todo_id)

        if not todo:
            raise TodoNotFoundError(todo_id)

        return dict(todo)

    async def list_todos(
        self, completed: Optional[bool] = None, limit: int = 100, offset: int = 0
    ) -> list[dict[str, Any]]:
        """List todos with optional filtering and pagination."""
        todos = await self.db.fetch_all(
            """
            SELECT * FROM {{tables.todos}}
            WHERE ($1::boolean IS NULL OR completed = $1)
            ORDER BY created_at DESC
            LIMIT $2 OFFSET $3
            """,
            completed,
            limit,
            offset,
        )

        return [dict(todo) for todo in todos]

    async def count_todos(self, completed: Optional[bool] = None) -> int:
        """Count todos with optional filtering."""
        count = await self.db.fetch_value(
            """
            SELECT COUNT(*) FROM {{tables.todos}}
            WHERE ($1::boolean IS NULL OR completed = $1)
            """,
            completed,
        )

        return count

    async def update_todo(
        self,
        todo_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        completed: Optional[bool] = None,
    ) -> dict[str, Any]:
        """Update a todo."""
        # Build dynamic update query
        updates = []
        params = []
        param_count = 1

        if title is not None:
            updates.append(f"title = ${param_count}")
            params.append(title)
            param_count += 1

        if description is not None:
            updates.append(f"description = ${param_count}")
            params.append(description)
            param_count += 1

        if completed is not None:
            updates.append(f"completed = ${param_count}")
            params.append(completed)
            param_count += 1

        if not updates:
            return await self.get_todo(todo_id)

        params.append(todo_id)
        query = f"""
            UPDATE {{{{tables.todos}}}}
            SET {', '.join(updates)}
            WHERE id = ${param_count}
            RETURNING *
        """

        todo = await self.db.fetch_one(query, *params)

        if not todo:
            raise TodoNotFoundError(todo_id)

        return dict(todo)

    async def delete_todo(self, todo_id: str) -> None:
        """Delete a todo."""
        result = await self.db.execute("DELETE FROM {{tables.todos}} WHERE id = $1", todo_id)

        if "0" in result:
            raise TodoNotFoundError(todo_id)

    async def complete_todo(self, todo_id: str) -> dict[str, Any]:
        """Mark a todo as completed."""
        return await self.update_todo(todo_id, completed=True)

    # Utility methods

    async def health_check(self) -> dict[str, Any]:
        """Check database health."""
        try:
            # Basic connectivity
            await self.db.fetch_value("SELECT 1")

            # Get stats
            pool_stats = await self.db.get_pool_stats()
            todo_count = await self.count_todos()

            return {
                "status": "healthy",
                "database": "connected",
                "pool": {
                    "size": pool_stats["size"],
                    "free": pool_stats["free_size"],
                    "used": pool_stats["used_size"],
                },
                "todos": {
                    "total": todo_count,
                    "completed": await self.count_todos(completed=True),
                    "pending": await self.count_todos(completed=False),
                },
            }
        except Exception as e:
            return {"status": "unhealthy", "database": "error", "error": str(e)}


# CLI support for migrations
if __name__ == "__main__":
    import asyncio

    async def run_migrations():
        db = TodoDatabase()
        await db.initialize()
        try:
            await db.apply_migrations()
        finally:
            await db.close()

    if len(sys.argv) > 1 and sys.argv[1] == "migrate":
        asyncio.run(run_migrations())
    else:
        print("Usage: python -m app.db migrate")
