# Copyright (c) 2025 Juan Reyero
# Licensed under the MIT License

# ABOUTME: Pytest fixtures for async database testing with automatic setup and teardown.
# ABOUTME: Provides test_db, test_db_with_schema, test_db_factory, test_db_with_tables, test_db_with_data, db_test_utils, and test_db_isolated fixtures.

"""
Ready-to-use pytest fixtures for async database testing.

Users can import these fixtures in their own tests by adding to their conftest.py:

    from pgdbm.fixtures.conftest import *

This provides:
- test_db: Basic test database
- test_db_with_schema: Test database with schema isolation
- test_db_factory: Factory for creating multiple test databases
"""

import os
from collections.abc import AsyncGenerator
from typing import Any, Optional

import pytest
import pytest_asyncio

from pgdbm.core import AsyncDatabaseManager, TransactionManager
from pgdbm.testing import AsyncTestDatabase, DatabaseTestCase, DatabaseTestConfig

# Default test configuration from environment
DEFAULT_TEST_CONFIG = DatabaseTestConfig(
    host=os.environ.get("TEST_DB_HOST", "localhost"),
    port=int(os.environ.get("TEST_DB_PORT", "5432")),
    user=os.environ.get("TEST_DB_USER", "postgres"),
    password=os.environ.get("TEST_DB_PASSWORD", "postgres"),
    verbose=os.environ.get("TEST_DB_VERBOSE", "").lower() in ("1", "true", "yes"),
    log_sql=os.environ.get("TEST_DB_LOG_SQL", "").lower() in ("1", "true", "yes"),
)


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[AsyncDatabaseManager, None]:
    """
    Provides a test database that is automatically created and destroyed.

    Usage:
        async def test_something(test_db):
            result = await test_db.fetch_one("SELECT 1")
            assert result["?column?"] == 1
    """
    test_database = AsyncTestDatabase(DEFAULT_TEST_CONFIG)
    await test_database.create_test_database()

    try:
        async with test_database.get_test_db_manager() as db_manager:
            yield db_manager
    finally:
        await test_database.drop_test_database()


@pytest_asyncio.fixture
async def test_db_with_schema() -> AsyncGenerator[AsyncDatabaseManager, None]:
    """
    Provides a test database with a custom schema for testing schema isolation.

    The schema will be named 'test_schema' and is automatically created.

    Usage:
        async def test_with_schema(test_db_with_schema):
            # Queries will use test_schema
            await test_db_with_schema.execute(
                "CREATE TABLE {{tables.users}} (id INT)"
            )
    """
    test_database = AsyncTestDatabase(DEFAULT_TEST_CONFIG)
    await test_database.create_test_database()

    try:
        async with test_database.get_test_db_manager(schema="test_schema") as db_manager:
            # Ensure schema exists
            await db_manager.execute('CREATE SCHEMA IF NOT EXISTS "test_schema"')
            yield db_manager
    finally:
        await test_database.drop_test_database()


@pytest_asyncio.fixture
async def test_db_factory() -> AsyncGenerator[Any, None]:
    """
    Factory fixture for creating multiple test databases in a single test.

    Usage:
        async def test_multiple_dbs(test_db_factory):
            db1 = await test_db_factory.create_db("db1")
            db2 = await test_db_factory.create_db("db2", schema="custom")

            # Use databases
            await db1.execute("CREATE TABLE test1 (id INT)")
            await db2.execute("CREATE TABLE test2 (id INT)")

            # Cleanup happens automatically
    """

    class TestDbFactory:
        def __init__(self) -> None:
            self.databases: list[tuple[AsyncTestDatabase, AsyncDatabaseManager]] = []

        async def create_db(
            self,
            suffix: Optional[str] = None,
            schema: Optional[str] = None,
            **kwargs: Any,
        ) -> AsyncDatabaseManager:
            test_database = AsyncTestDatabase(DEFAULT_TEST_CONFIG)
            await test_database.create_test_database(suffix)

            config = test_database.get_test_db_config(schema=schema, **kwargs)
            db_manager = AsyncDatabaseManager(config)
            try:
                await db_manager.connect()
                if schema:
                    await db_manager.execute(f'CREATE SCHEMA IF NOT EXISTS "{schema}"')
            except Exception:
                await db_manager.disconnect()
                await test_database.drop_test_database()
                raise

            self.databases.append((test_database, db_manager))
            return db_manager

        async def cleanup(self) -> None:
            for test_database, db_manager in self.databases:
                await db_manager.disconnect()
                await test_database.drop_test_database()

    factory = TestDbFactory()
    try:
        yield factory
    finally:
        await factory.cleanup()


@pytest_asyncio.fixture
async def test_db_with_tables(
    test_db: AsyncDatabaseManager,
) -> AsyncGenerator[AsyncDatabaseManager, None]:
    """
    Provides a test database with common tables pre-created.

    Tables created:
    - users (id, email, full_name, is_active, created_at)
    - projects (id, name, owner_id, description, created_at)
    - agents (id, project_id, title, status, assigned_to, created_at)
    """
    # Create users table
    await test_db.execute(
        """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            full_name VARCHAR(255),
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Create projects table
    await test_db.execute(
        """
        CREATE TABLE projects (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            owner_id INTEGER REFERENCES users(id),
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Create agents table
    await test_db.execute(
        """
        CREATE TABLE agents (
            id SERIAL PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id),
            title VARCHAR(255) NOT NULL,
            status VARCHAR(50) DEFAULT 'pending',
            assigned_to INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    yield test_db


@pytest_asyncio.fixture
async def test_db_with_data(
    test_db_with_tables: AsyncDatabaseManager,
) -> AsyncGenerator[AsyncDatabaseManager, None]:
    """
    Provides a test database with tables and sample data.

    Sample data includes:
    - 3 users (alice, bob, charlie)
    - 2 projects owned by alice
    - 5 agents distributed across projects
    """
    db = test_db_with_tables

    # Insert users
    await db.execute(
        """
        INSERT INTO users (email, full_name) VALUES
        ('alice@example.com', 'Alice Smith'),
        ('bob@example.com', 'Bob Jones'),
        ('charlie@example.com', 'Charlie Brown')
    """
    )

    # Insert projects
    alice_id = await db.fetch_value("SELECT id FROM users WHERE email = 'alice@example.com'")

    await db.execute(
        """
        INSERT INTO projects (name, owner_id, description) VALUES
        ('Project Alpha', $1, 'First project'),
        ('Project Beta', $1, 'Second project')
    """,
        alice_id,
    )

    # Insert agents
    project_alpha_id = await db.fetch_value("SELECT id FROM projects WHERE name = 'Project Alpha'")
    project_beta_id = await db.fetch_value("SELECT id FROM projects WHERE name = 'Project Beta'")
    bob_id = await db.fetch_value("SELECT id FROM users WHERE email = 'bob@example.com'")

    await db.execute(
        """
        INSERT INTO agents (project_id, title, status, assigned_to) VALUES
        ($1, 'Design database schema', 'completed', $3),
        ($1, 'Implement user authentication', 'in_progress', $3),
        ($1, 'Write tests', 'pending', NULL),
        ($2, 'Setup CI/CD', 'in_progress', $3),
        ($2, 'Deploy to production', 'pending', NULL)
    """,
        project_alpha_id,
        project_beta_id,
        bob_id,
    )

    yield db


@pytest.fixture  # type: ignore[misc]
def db_test_utils(test_db: AsyncDatabaseManager) -> DatabaseTestCase:
    """
    Provides database test utilities for assertions and helpers.

    Usage:
        async def test_something(test_db, db_test_utils):
            # Create test data
            user = await db_test_utils.create_test_user("test@example.com")

            # Count rows
            count = await db_test_utils.count_rows("users")
            assert count == 1

            # Check table exists
            assert await db_test_utils.table_exists("users")
    """
    return DatabaseTestCase(test_db)


@pytest_asyncio.fixture
async def test_db_isolated(
    test_db: AsyncDatabaseManager,
) -> AsyncGenerator[TransactionManager, None]:
    """
    Provides a test database with transaction isolation for each test.

    All changes are rolled back after the test, keeping the database clean.

    Usage:
        async def test_isolated(test_db_isolated):
            # test_db_isolated is a TransactionManager with the same API as AsyncDatabaseManager
            await test_db_isolated.execute("INSERT INTO users ...")
            result = await test_db_isolated.fetch_one("SELECT * FROM users")
            # Changes are automatically rolled back
    """
    async with test_db.transaction() as conn:
        # Create a savepoint we can rollback to
        await conn.execute("SAVEPOINT test_isolation")

        # Yield the transaction manager for the test
        yield conn

        # Rollback to savepoint
        await conn.execute("ROLLBACK TO SAVEPOINT test_isolation")
