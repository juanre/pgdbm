"""
Tests for shared connection pool functionality.
"""

import asyncpg
import pytest

from pgdbm import AsyncDatabaseManager, ConfigurationError, DatabaseConfig, PoolError
from pgdbm.monitoring import MonitoredAsyncDatabaseManager


@pytest.mark.unit
def test_shared_pool_init_validation():
    """Test parameter validation for shared pool initialization."""
    config = DatabaseConfig()
    pool = object()  # Mock pool for validation tests

    # Cannot provide both config and pool
    with pytest.raises(ConfigurationError, match="Cannot provide both config and pool"):
        AsyncDatabaseManager(config=config, pool=pool)

    # Must provide either config or pool
    with pytest.raises(ConfigurationError, match="Must provide either config or pool"):
        AsyncDatabaseManager()

    # Schema override only valid with external pool
    with pytest.raises(ConfigurationError, match="Schema override only valid with external pool"):
        AsyncDatabaseManager(config=config, schema="custom")

    # Valid initialization with config
    db = AsyncDatabaseManager(config=config)
    assert db.config == config
    assert db._external_pool is False

    # Valid initialization with pool
    db = AsyncDatabaseManager(pool=pool)
    assert db._pool == pool
    assert db._external_pool is True
    assert db.schema == "public"  # Default schema

    # Valid initialization with pool and schema
    db = AsyncDatabaseManager(pool=pool, schema="custom")
    assert db._pool == pool
    assert db.schema == "custom"
    assert db._external_pool is True


@pytest.mark.integration
async def test_shared_pool_creation(test_db_manager):
    """Test creating a shared connection pool."""
    # Get config from existing test database
    config = test_db_manager.config
    config.min_connections = 2
    config.max_connections = 5

    # Create shared pool
    pool = await AsyncDatabaseManager.create_shared_pool(config)

    try:
        # Verify pool is created and functional
        assert pool is not None
        assert isinstance(pool, asyncpg.Pool)
        assert pool.get_min_size() == 2
        assert pool.get_max_size() == 5

        # Test pool is functional
        async with pool.acquire() as conn:
            result = await conn.fetchval("SELECT 1")
            assert result == 1

    finally:
        await pool.close()


@pytest.mark.integration
async def test_multiple_managers_shared_pool(test_db_manager):
    """Test multiple database managers sharing the same pool."""
    # Get config from existing test database
    config = test_db_manager.config
    config.min_connections = 5
    config.max_connections = 10

    # Create shared pool
    pool = await AsyncDatabaseManager.create_shared_pool(config)

    try:
        # Create multiple managers with different schemas
        task_db = AsyncDatabaseManager(pool=pool, schema="agents")
        user_db = AsyncDatabaseManager(pool=pool, schema="users")
        admin_db = AsyncDatabaseManager(pool=pool, schema="admin")

        # Verify all managers share the same pool
        assert task_db._pool is pool
        assert user_db._pool is pool
        assert admin_db._pool is pool

        # Verify different schemas
        assert task_db.schema == "agents"
        assert user_db.schema == "users"
        assert admin_db.schema == "admin"

        # Create schemas
        await task_db.execute("CREATE SCHEMA IF NOT EXISTS agents")
        await user_db.execute("CREATE SCHEMA IF NOT EXISTS users")
        await admin_db.execute("CREATE SCHEMA IF NOT EXISTS admin")

        # Create tables in different schemas
        await task_db.execute(
            """
            CREATE TABLE IF NOT EXISTS {{tables.items}} (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL
            )
        """
        )

        await user_db.execute(
            """
            CREATE TABLE IF NOT EXISTS {{tables.items}} (
                id SERIAL PRIMARY KEY,
                name TEXT NOT NULL
            )
        """
        )

        # Insert data
        await task_db.execute("INSERT INTO {{tables.items}} (name) VALUES ($1)", "Agent Item")
        await user_db.execute("INSERT INTO {{tables.items}} (name) VALUES ($1)", "User Item")

        # Verify data isolation between schemas
        task_items = await task_db.fetch_all("SELECT * FROM {{tables.items}}")
        user_items = await user_db.fetch_all("SELECT * FROM {{tables.items}}")

        assert len(task_items) == 1
        assert task_items[0]["name"] == "Agent Item"

        assert len(user_items) == 1
        assert user_items[0]["name"] == "User Item"

        # Verify pool stats are identical
        task_stats = await task_db.get_pool_stats()
        user_stats = await user_db.get_pool_stats()

        # Compare pool-related stats (not schema-specific stats)
        assert task_stats["min_size"] == user_stats["min_size"]
        assert task_stats["max_size"] == user_stats["max_size"]
        assert task_stats["size"] == user_stats["size"]

    finally:
        await pool.close()


@pytest.mark.integration
async def test_external_pool_restrictions(test_db_manager):
    """Test that external pool managers cannot connect/disconnect."""
    config = test_db_manager.config
    pool = await AsyncDatabaseManager.create_shared_pool(config)

    try:
        db = AsyncDatabaseManager(pool=pool, schema="test")

        # Cannot connect when using external pool
        with pytest.raises(PoolError, match="Cannot call connect"):
            await db.connect()

        # Disconnect should do nothing (no error)
        await db.disconnect()  # Should not raise

        # Pool should still be functional
        result = await db.fetch_one("SELECT 1 as val")
        assert result["val"] == 1

    finally:
        await pool.close()


@pytest.mark.integration
async def test_backward_compatibility(test_db_manager):
    """Test that traditional usage still works."""
    # Create new config based on test database
    config = DatabaseConfig(
        host=test_db_manager.config.host,
        port=test_db_manager.config.port,
        database=test_db_manager.config.database,
        user=test_db_manager.config.user,
        password=test_db_manager.config.password,
        schema="myapp",  # Use 'schema' alias instead of 'schema_name'
        min_connections=2,
        max_connections=5,
    )

    # Create manager the traditional way
    db = AsyncDatabaseManager(config)

    # Should be able to connect
    await db.connect()

    try:
        # Verify it creates its own pool
        assert db._pool is not None
        assert db._external_pool is False
        assert db.config.schema_name == "myapp"
        assert db.schema == "myapp"

        # Test basic operations
        await db.execute("CREATE SCHEMA IF NOT EXISTS myapp")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS {{tables.test}} (
                id SERIAL PRIMARY KEY,
                value TEXT
            )
        """
        )

        await db.execute("INSERT INTO {{tables.test}} (value) VALUES ($1)", "test_value")

        result = await db.fetch_one("SELECT * FROM {{tables.test}}")
        assert result["value"] == "test_value"

        # Get pool stats
        stats = await db.get_pool_stats()
        assert stats["status"] == "connected"
        assert stats["min_size"] == 2
        assert stats["max_size"] == 5

    finally:
        await db.disconnect()


@pytest.mark.integration
async def test_monitored_manager_with_shared_pool(test_db_manager):
    """Test MonitoredAsyncDatabaseManager with shared pool."""
    config = test_db_manager.config
    pool = await AsyncDatabaseManager.create_shared_pool(config)

    try:
        # Create monitored manager with shared pool
        db = MonitoredAsyncDatabaseManager(
            pool=pool, schema="monitoring", slow_query_threshold_ms=100
        )

        assert db._pool is pool
        assert db._external_pool is True
        assert db.schema == "monitoring"
        assert db._slow_query_threshold_ms == 100.0

        # Test that monitoring works
        await db.execute("CREATE SCHEMA IF NOT EXISTS monitoring")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS {{tables.logs}} (
                id SERIAL PRIMARY KEY,
                message TEXT
            )
        """
        )

        # Insert some data
        for i in range(3):
            await db.execute(
                "INSERT INTO {{tables.logs}} (message) VALUES ($1)", f"Log message {i}"
            )

        # Verify monitoring tracked the queries
        assert db._queries_executed > 0

        # Get metrics
        metrics = await db.get_metrics()
        assert metrics.queries_executed > 0

    finally:
        await pool.close()


@pytest.mark.integration
async def test_schema_placeholder_replacement(test_db_manager):
    """Test that schema placeholders work correctly with shared pools."""
    config = test_db_manager.config
    pool = await AsyncDatabaseManager.create_shared_pool(config)

    try:
        # Test with custom schema
        db = AsyncDatabaseManager(pool=pool, schema="custom")

        # Create schema and table
        await db.execute("CREATE SCHEMA IF NOT EXISTS custom")
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS {{schema}}.test_table (
                id SERIAL PRIMARY KEY
            )
        """
        )

        # Verify table was created in correct schema
        result = await db.fetch_one(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema = 'custom' AND table_name = 'test_table'
        """
        )
        assert result is not None
        assert result["table_schema"] == "custom"

        # Test {{tables.name}} placeholder
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS {{tables.another_table}} (
                id SERIAL PRIMARY KEY
            )
        """
        )

        # Verify it was created as custom.another_table
        result = await db.fetch_one(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_schema = 'custom' AND table_name = 'another_table'
        """
        )
        assert result is not None

    finally:
        await pool.close()


@pytest.mark.integration
async def test_pool_lifecycle(test_db_manager):
    """Test proper pool lifecycle management."""
    config = test_db_manager.config
    config.min_connections = 2
    config.max_connections = 4

    # Create and close pool multiple times
    for i in range(3):
        pool = await AsyncDatabaseManager.create_shared_pool(config)

        # Create managers
        db1 = AsyncDatabaseManager(pool=pool, schema=f"schema_{i}_1")
        db2 = AsyncDatabaseManager(pool=pool, schema=f"schema_{i}_2")

        # Do some work
        await db1.execute(f"CREATE SCHEMA IF NOT EXISTS schema_{i}_1")
        await db2.execute(f"CREATE SCHEMA IF NOT EXISTS schema_{i}_2")

        # Close pool
        await pool.close()

        # Verify pool is closed
        with pytest.raises(asyncpg.InterfaceError):
            await db1.fetch_one("SELECT 1")
