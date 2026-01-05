# Copyright (c) 2025 Juan Reyero
# Licensed under the MIT License

# ABOUTME: Test database utilities for creating isolated test databases, fixtures, and helper functions for testing.
# ABOUTME: Provides AsyncTestDatabase, DatabaseTestCase, and DatabaseTestConfig for async pytest-based tests.

"""
Testing utilities for async database operations with debugging support.
"""

import json
import logging
import os
import re
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

import asyncpg
from pydantic import BaseModel

from pgdbm.core import AsyncDatabaseManager, DatabaseConfig
from pgdbm.errors import ConfigurationError, DatabaseTestError

logger = logging.getLogger(__name__)


class DatabaseTestConfig(BaseModel):
    """Configuration for test databases."""

    # Base connection info (usually to postgres database)
    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = "postgres"

    # Test database settings
    test_db_prefix: str = "test_"
    test_db_template: str = "template0"
    drop_on_cleanup: bool = True

    # Test data settings
    fixtures_path: Optional[str] = None
    seed_data_path: Optional[str] = None

    # Debugging
    verbose: bool = False
    log_sql: bool = False

    @classmethod
    def from_env(cls) -> "DatabaseTestConfig":
        """Create config from environment variables."""
        return cls(
            host=os.environ.get("TEST_DB_HOST", "localhost"),
            port=int(os.environ.get("TEST_DB_PORT", "5432")),
            user=os.environ.get("TEST_DB_USER", "postgres"),
            password=os.environ.get("TEST_DB_PASSWORD", "postgres"),
            verbose=os.environ.get("TEST_DB_VERBOSE", "").lower() in ("1", "true", "yes"),
            log_sql=os.environ.get("TEST_DB_LOG_SQL", "").lower() in ("1", "true", "yes"),
        )


class AsyncTestDatabase:
    """Test database management for async tests with debugging."""

    def __init__(self, config: Optional[DatabaseTestConfig] = None):
        self.config = config or DatabaseTestConfig.from_env()
        self._test_db_name: Optional[str] = None
        self._admin_pool: Optional[asyncpg.Pool] = None
        self._start_time: Optional[datetime] = None
        self._queries_executed: int = 0

    async def _get_admin_pool(self) -> asyncpg.Pool:
        """Get or create admin connection pool."""
        if not self._admin_pool:
            dsn = (
                f"postgresql://{self.config.user}:{self.config.password}@"
                f"{self.config.host}:{self.config.port}/postgres"
            )
            self._admin_pool = await asyncpg.create_pool(
                dsn,
                min_size=1,
                max_size=2,
            )
        return self._admin_pool

    @classmethod
    @asynccontextmanager
    async def create(
        cls,
        schema: Optional[str] = None,
        config: Optional[DatabaseTestConfig] = None,
        suffix: Optional[str] = None,
        **kwargs: Any,
    ) -> AsyncGenerator[AsyncDatabaseManager, None]:
        """Create a temporary test database and yield a connected manager."""
        test_database = cls(config)
        await test_database.create_test_database(suffix=suffix)
        try:
            async with test_database.get_test_db_manager(schema=schema, **kwargs) as db_manager:
                yield db_manager
        finally:
            await test_database.drop_test_database()

    async def create_test_database(self, suffix: Optional[str] = None) -> str:
        """
        Create a test database with unique name.

        Args:
            suffix: Optional suffix for the database name

        Returns:
            Name of the created test database
        """
        self._start_time = datetime.now()

        # Generate unique test database name
        unique_id = uuid.uuid4().hex[:8]
        suffix_part = f"_{suffix}" if suffix else ""
        self._test_db_name = f"{self.config.test_db_prefix}{unique_id}{suffix_part}"

        if self.config.verbose:
            logger.info(f"Creating test database: {self._test_db_name}")

        pool = await self._get_admin_pool()

        async with pool.acquire() as conn:
            # Check if database already exists
            exists = await conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", self._test_db_name
            )

            if exists:
                if self.config.verbose:
                    logger.warning(
                        f"Test database '{self._test_db_name}' already exists, dropping it"
                    )
                await self._drop_database(conn, self._test_db_name)

            # Validate database name and template before creation
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$", self._test_db_name):
                raise DatabaseTestError(
                    f"Invalid test database name: {self._test_db_name}",
                    test_db_name=self._test_db_name,
                )

            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$", self.config.test_db_template):
                raise DatabaseTestError(
                    f"Invalid template name: {self.config.test_db_template}. "
                    "Template names must start with a letter or underscore and "
                    "contain only letters, numbers, and underscores."
                )

            # Create test database
            await conn.execute(
                f'CREATE DATABASE "{self._test_db_name}" WITH TEMPLATE {self.config.test_db_template}'
            )

            if self.config.verbose:
                logger.info(f"Created test database: {self._test_db_name}")

        return self._test_db_name

    async def _drop_database(
        self,
        conn: Union[asyncpg.Connection, asyncpg.pool.PoolConnectionProxy],
        db_name: str,
    ) -> None:
        """Drop a database, terminating any existing connections first."""
        # Validate database name to prevent SQL injection
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$", db_name):
            raise DatabaseTestError(
                f"Invalid database name '{db_name}'. Database names must start with a "
                "letter or underscore and contain only letters, numbers, and underscores.",
                test_db_name=db_name,
            )

        # Terminate all connections to the database using parameterized query
        await conn.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = $1
            AND pid <> pg_backend_pid()
        """,
            db_name,
        )

        # Drop the database - we still need to use identifier here
        # but the name is now validated
        await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')

    async def drop_test_database(self) -> None:
        """Drop the test database and clean up resources."""
        if not self._test_db_name:
            return

        if self.config.verbose:
            duration = datetime.now() - self._start_time if self._start_time else None
            logger.info(
                f"Dropping test database: {self._test_db_name} "
                f"(existed for {duration}, {self._queries_executed} queries executed)"
            )

        if self.config.drop_on_cleanup:
            pool = await self._get_admin_pool()
            async with pool.acquire() as conn:
                await self._drop_database(conn, self._test_db_name)

            if self.config.verbose:
                logger.info(f"Dropped test database: {self._test_db_name}")
        else:
            logger.warning(
                f"Test database '{self._test_db_name}' was not dropped (drop_on_cleanup=False)"
            )

        # Clean up admin pool
        if self._admin_pool:
            await self._admin_pool.close()
            self._admin_pool = None

        self._test_db_name = None

    def get_test_db_config(self, schema: Optional[str] = None, **kwargs: Any) -> DatabaseConfig:
        """
        Get database configuration for the test database.

        Args:
            schema: Optional schema name
            **kwargs: Additional config overrides

        Returns:
            DatabaseConfig for the test database
        """
        if not self._test_db_name:
            raise DatabaseTestError(
                "Test database not created. Call create_test_database() first.",
                test_db_name=self._test_db_name,
            )

        config = DatabaseConfig(
            host=self.config.host,
            port=self.config.port,
            database=self._test_db_name,
            user=self.config.user,
            password=self.config.password,
            schema=schema,
            min_connections=2,
            max_connections=5,  # Lower for tests
            **kwargs,
        )

        # Enable SQL logging if requested
        if self.config.log_sql:
            os.environ["DB_DEBUG"] = "1"

        return config

    @asynccontextmanager
    async def get_test_db_manager(
        self, schema: Optional[str] = None, **kwargs: Any
    ) -> AsyncGenerator[AsyncDatabaseManager, None]:
        """
        Get a database manager for the test database.

        This is a context manager that handles connection lifecycle.
        """
        config = self.get_test_db_config(schema, **kwargs)
        db_manager = AsyncDatabaseManager(config)

        # Track queries if verbose
        if self.config.verbose:
            original_execute = db_manager.execute

            async def tracked_execute(*args: Any, **kwargs: Any) -> str:
                self._queries_executed += 1
                result: str = await original_execute(*args, **kwargs)
                return result

            db_manager.execute = tracked_execute  # type: ignore[method-assign]

        await db_manager.connect()

        try:
            yield db_manager
        finally:
            stats = await db_manager.get_pool_stats()
            if self.config.verbose:
                logger.info(f"Test database pool stats: {stats}")
            await db_manager.disconnect()

    async def load_fixtures(
        self, db_manager: AsyncDatabaseManager, fixtures_path: Union[str, Path]
    ) -> dict[str, int]:
        """
        Load test fixtures from SQL or JSON files.

        Args:
            db_manager: Database manager to use
            fixtures_path: Path to fixtures file or directory

        Returns:
            Dictionary with table names and row counts
        """
        fixtures_path = Path(fixtures_path)
        loaded = {}

        if fixtures_path.is_file():
            files = [fixtures_path]
        elif fixtures_path.is_dir():
            files = list(fixtures_path.glob("*.sql")) + list(fixtures_path.glob("*.json"))
        else:
            raise ConfigurationError(
                f"Fixtures path does not exist: {fixtures_path}",
                config_field="fixtures_path",
            )

        for file in sorted(files):
            if self.config.verbose:
                logger.info(f"Loading fixtures from: {file.name}")

            if file.suffix == ".sql":
                # Load SQL fixtures
                content = file.read_text()
                await db_manager.execute(content)
                loaded[file.stem] = -1  # Unknown count for SQL

            elif file.suffix == ".json":
                # Load JSON fixtures
                data = json.loads(file.read_text())
                for table_name, rows in data.items():
                    if rows:
                        # Insert rows
                        columns = list(rows[0].keys())
                        values = [tuple(row.values()) for row in rows]

                        placeholders = ", ".join(f"${i+1}" for i in range(len(columns)))
                        query = f"""
                            INSERT INTO {table_name} ({", ".join(columns)})
                            VALUES ({placeholders})
                        """

                        await db_manager.executemany(query, values)
                        loaded[table_name] = len(rows)

                        if self.config.verbose:
                            logger.info(f"Loaded {len(rows)} rows into {table_name}")

        return loaded

    async def snapshot_table(
        self,
        db_manager: AsyncDatabaseManager,
        table_name: str,
        order_by: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """
        Create a snapshot of a table's data for comparison.

        Useful for testing that operations have expected effects.
        """
        query = f"SELECT * FROM {table_name}"
        if order_by:
            query += f" ORDER BY {order_by}"

        result: list[dict[str, Any]] = await db_manager.fetch_all(query)
        return result

    async def assert_table_unchanged(
        self,
        db_manager: AsyncDatabaseManager,
        table_name: str,
        before_snapshot: list[dict[str, Any]],
        order_by: Optional[str] = None,
    ) -> None:
        """Assert that a table's data hasn't changed."""
        after_snapshot = await self.snapshot_table(db_manager, table_name, order_by)

        if before_snapshot != after_snapshot:
            # Find differences for better error message
            before_set = {json.dumps(row, sort_keys=True) for row in before_snapshot}
            after_set = {json.dumps(row, sort_keys=True) for row in after_snapshot}

            added = after_set - before_set
            removed = before_set - after_set

            raise AssertionError(
                f"Table '{table_name}' has changed!\n"
                f"Added rows: {len(added)}\n"
                f"Removed rows: {len(removed)}"
            )


class DatabaseTestCase:
    """Base class for database test cases with utilities."""

    def __init__(self, db_manager: AsyncDatabaseManager):
        self.db = db_manager

    async def create_test_user(self, email: Optional[str] = None, **kwargs: Any) -> dict[str, Any]:
        """Create a test user with defaults."""
        email = email or f"test_{uuid.uuid4().hex[:8]}@example.com"

        user_id = await self.db.execute_and_return_id(
            """
            INSERT INTO users (email, full_name, is_active)
            VALUES ($1, $2, $3)
            """,
            email,
            kwargs.get("full_name", "Test User"),
            kwargs.get("is_active", True),
        )

        return {"id": user_id, "email": email, **kwargs}

    async def count_rows(self, table_name: str, where: Optional[str] = None) -> int:
        """Count rows in a table with optional WHERE clause."""
        query = f"SELECT COUNT(*) FROM {table_name}"
        if where:
            query += f" WHERE {where}"

        count = await self.db.fetch_value(query)
        return int(count) if count is not None else 0

    async def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        result: bool = await self.db.table_exists(table_name)
        return result

    async def truncate_table(self, table_name: str, cascade: bool = False) -> None:
        """Truncate a table (remove all rows)."""
        cascade_clause = "CASCADE" if cascade else ""
        await self.db.execute(f"TRUNCATE TABLE {table_name} {cascade_clause}")
