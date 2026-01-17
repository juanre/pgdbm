"""
Tests for core async database functionality.
"""

import asyncpg
import pytest

from pgdbm import AsyncDatabaseManager, DatabaseConfig


@pytest.mark.unit
def test_database_config():
    """Test DatabaseConfig creation and defaults."""
    # Test with minimal config
    config = DatabaseConfig()
    assert config.host == "localhost"
    assert config.port == 5432
    assert config.database == "postgres"
    assert config.user == "postgres"
    assert config.min_connections == 10
    assert config.max_connections == 20

    # Test with custom values
    config = DatabaseConfig(
        host="db.example.com",
        port=5433,
        schema="myapp",
        min_connections=5,
        max_connections=15,
    )
    assert config.host == "db.example.com"
    assert config.port == 5433
    assert config.schema_name == "myapp"
    assert config.min_connections == 5
    assert config.max_connections == 15

    # Test DSN generation with masked password (doesn't require password)
    assert "db.example.com:5433" in config.get_dsn_masked()


@pytest.mark.unit
def test_database_config_dsn():
    """Test DSN generation from config."""
    # Test with connection string
    config = DatabaseConfig(connection_string="postgresql://user:pass@host:5433/mydb")
    assert config.get_dsn() == "postgresql://user:pass@host:5433/mydb"

    # Test with individual parameters
    config = DatabaseConfig(
        user="testuser",
        password="testpass",
        host="testhost",
        port=5433,
        database="testdb",
    )
    assert config.get_dsn() == "postgresql://testuser:testpass@testhost:5433/testdb"


@pytest.mark.unit
def test_database_config_password_required():
    """Test that password is required for DSN generation."""
    from pgdbm import ConfigurationError

    # Test that get_dsn() raises error without password
    config = DatabaseConfig(host="localhost", database="testdb")
    with pytest.raises(ConfigurationError) as exc_info:
        config.get_dsn()

    assert "Database password not provided" in str(exc_info.value)
    assert exc_info.value.config_field == "password"

    # Test that get_dsn_masked() works without password
    masked_dsn = config.get_dsn_masked()
    assert "****" in masked_dsn
    assert "localhost" in masked_dsn


@pytest.mark.integration
async def test_connection_pool_lifecycle(test_db_manager):
    """Test connection pool creation and lifecycle."""
    # Pool should be connected from fixture
    stats = await test_db_manager.get_pool_stats()
    assert stats["status"] == "connected"
    assert stats["min_size"] > 0
    assert stats["max_size"] > 0

    # Test basic query
    result = await test_db_manager.fetch_value("SELECT 1")
    assert result == 1

    # Test database info
    db_info = await test_db_manager.fetch_one(
        "SELECT current_database() as db, version() as version"
    )
    assert db_info["db"] is not None
    assert "PostgreSQL" in db_info["version"]


@pytest.mark.integration
async def test_query_preparation(test_db_with_schema):
    """Test query preparation with schema placeholders."""
    # Test schema placeholder - now with quotes for security
    query = "SELECT * FROM {{schema}}.users"
    prepared = test_db_with_schema._prepare_query(query)
    assert prepared == 'SELECT * FROM "test_schema".users'

    # Test table placeholder - now with quoted schema
    query = "SELECT * FROM {{tables.users}}"
    prepared = test_db_with_schema._prepare_query(query)
    assert prepared == 'SELECT * FROM "test_schema".users'

    # Test explicit schema + table placeholder (cross-schema queries)
    query = "SELECT * FROM {{tables.server.projects}}"
    prepared = test_db_with_schema._prepare_query(query)
    assert prepared == 'SELECT * FROM "server".projects'

    # Test without schema
    db_no_schema = AsyncDatabaseManager(DatabaseConfig(schema=None))
    query = "SELECT * FROM {{tables.users}}"
    prepared = db_no_schema._prepare_query(query)
    assert prepared == "SELECT * FROM users"

    # Test explicit schema works even when manager has no schema
    query = "SELECT * FROM {{tables.server.projects}}"
    prepared = db_no_schema._prepare_query(query)
    assert prepared == 'SELECT * FROM "server".projects'


@pytest.mark.integration
async def test_basic_operations(sample_tables):
    """Test basic CRUD operations."""
    db = sample_tables

    # Test fetch_all
    users = await db.fetch_all("SELECT * FROM users ORDER BY email")
    assert len(users) == 3
    assert users[0]["email"] == "alice@example.com"

    # Test fetch_one
    user = await db.fetch_one("SELECT * FROM users WHERE email = $1", "bob@example.com")
    assert user["full_name"] == "Bob Jones"

    # Test fetch_value
    count = await db.fetch_value("SELECT COUNT(*) FROM users")
    assert count == 3

    # Test execute_and_return_id
    new_id = await db.execute_and_return_id(
        "INSERT INTO users (email, full_name) VALUES ($1, $2)",
        "dave@example.com",
        "Dave Wilson",
    )
    assert new_id is not None

    # Verify insertion
    new_user = await db.fetch_one(
        "SELECT * FROM users WHERE id = $1", int(new_id)  # Convert string ID to int
    )
    assert new_user["email"] == "dave@example.com"


@pytest.mark.integration
async def test_transaction_commit(sample_tables):
    """Test transaction commit behavior."""
    db = sample_tables

    # Use transaction context
    async with db.transaction() as tx:
        await tx.execute(
            "INSERT INTO users (email, full_name) VALUES ($1, $2)",
            "transaction@example.com",
            "Transaction User",
        )

        # Query within transaction should see the new row
        result = await tx.fetch_one(
            "SELECT * FROM users WHERE email = $1", "transaction@example.com"
        )
        assert result is not None

    # After transaction, row should be committed
    user = await db.fetch_one("SELECT * FROM users WHERE email = $1", "transaction@example.com")
    assert user is not None
    assert user["full_name"] == "Transaction User"


@pytest.mark.integration
async def test_transaction_rollback(sample_tables):
    """Test transaction rollback behavior."""
    db = sample_tables

    initial_count = await db.fetch_value("SELECT COUNT(*) FROM users")

    # Use transaction context with intentional error
    with pytest.raises(asyncpg.UndefinedTableError):
        async with db.transaction() as tx:
            await tx.execute(
                "INSERT INTO users (email, full_name) VALUES ($1, $2)",
                "rollback@example.com",
                "Rollback User",
            )

            # Force a database error by querying non-existent table
            await tx.execute("SELECT * FROM non_existent_table")

    # After rollback, row should not exist
    user = await db.fetch_one("SELECT * FROM users WHERE email = $1", "rollback@example.com")
    assert user is None

    # Count should be unchanged
    final_count = await db.fetch_value("SELECT COUNT(*) FROM users")
    assert final_count == initial_count


@pytest.mark.integration
async def test_table_exists(sample_tables):
    """Test table existence checking."""
    db = sample_tables

    # Test existing tables
    assert await db.table_exists("users") is True
    assert await db.table_exists("projects") is True
    assert await db.table_exists("agents") is True

    # Test non-existing table
    assert await db.table_exists("non_existing_table") is False

    # Test with schema qualification (if schema is set)
    if db.schema:
        assert await db.table_exists(f"{db.schema}.users") is True


@pytest.mark.integration
async def test_prepared_statements(test_db_manager):
    """Test prepared statement functionality."""
    db = test_db_manager

    # Create a simple table
    await db.execute(
        """
        CREATE TABLE test_prepared (
            id SERIAL PRIMARY KEY,
            value INTEGER NOT NULL
        )
    """
    )

    # Add a prepared statement
    db.add_prepared_statement(
        "insert_value", "INSERT INTO test_prepared (value) VALUES ($1) RETURNING id"
    )

    # Note: Prepared statements are created on connection init,
    # so we need a new connection to test
    # For now, just verify the statement was added
    assert "insert_value" in db._prepared_statements


@pytest.mark.integration
async def test_connection_acquire_context(test_db_manager):
    """Test manual connection acquisition."""
    db = test_db_manager

    # Use acquire context
    async with db.acquire() as conn:
        # Direct connection operations
        result = await conn.fetchval("SELECT 42")
        assert result == 42

        # Multiple operations on same connection
        await conn.execute("CREATE TEMP TABLE temp_test (id INT)")
        await conn.execute("INSERT INTO temp_test VALUES (1), (2), (3)")
        count = await conn.fetchval("SELECT COUNT(*) FROM temp_test")
        assert count == 3

    # Temp table should not exist outside the connection
    # Note: Temp tables in PostgreSQL are connection-specific
    # So we can't test this easily without a new connection


@pytest.mark.integration
async def test_pool_stats(test_db_manager):
    """Test connection pool statistics."""
    db = test_db_manager

    stats = await db.get_pool_stats()

    # Check required fields
    assert "status" in stats
    assert stats["status"] == "connected"
    assert "min_size" in stats
    assert "max_size" in stats
    assert "size" in stats
    assert "free_size" in stats
    assert "used_size" in stats

    # Sanity checks
    assert stats["size"] >= stats["min_size"]
    assert stats["size"] <= stats["max_size"]
    assert stats["free_size"] >= 0
    assert stats["used_size"] >= 0
    assert stats["free_size"] + stats["used_size"] == stats["size"]
