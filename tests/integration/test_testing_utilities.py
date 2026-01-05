# Copyright (c) 2025 Juan Reyero
# Licensed under the MIT License

"""
Integration tests for testing utilities and fixtures.

These tests demonstrate how to use pgdbm's testing features in test suites.
"""

import json
import tempfile
from pathlib import Path

import asyncpg
import pytest

from pgdbm import AsyncTestDatabase, DatabaseTestCase, DatabaseTestConfig

# Fixtures are imported via conftest.py


class TestTestingUtilities:
    """Test the testing utilities provided by pgdbm."""

    @pytest.mark.asyncio
    async def test_test_database_lifecycle(self):
        """Test AsyncTestDatabase creation and cleanup."""
        config = DatabaseTestConfig(
            host="localhost",
            user="postgres",
            password="postgres",
            test_db_prefix="integration_test_",
            verbose=True,
        )

        test_database = AsyncTestDatabase(config)

        # Create test database
        db_name = await test_database.create_test_database(suffix="lifecycle")
        assert db_name.startswith("integration_test_")
        assert "lifecycle" in db_name

        # Get database manager
        async with test_database.get_test_db_manager() as db:
            # Verify we can use the database
            result = await db.fetch_one("SELECT current_database() as db")
            assert result["db"] == db_name

            # Create a table
            await db.execute("CREATE TABLE test (id INT)")
            assert await db.table_exists("test")

        # Drop test database
        await test_database.drop_test_database()

        # Verify cleanup (would fail if database still exists)
        # Creating again with same name should work
        await test_database.create_test_database(suffix="lifecycle")
        await test_database.drop_test_database()

    @pytest.mark.asyncio
    async def test_async_test_database_create_context_manager(self):
        """Ensure AsyncTestDatabase.create cleans up the database."""
        config = DatabaseTestConfig.from_env()
        async with AsyncTestDatabase.create(schema="test", config=config) as db:
            db_name = await db.fetch_value("SELECT current_database()")

        admin_conn = await asyncpg.connect(
            user=config.user,
            password=config.password,
            host=config.host,
            port=config.port,
            database="postgres",
        )
        try:
            exists = await admin_conn.fetchval(
                "SELECT 1 FROM pg_database WHERE datname = $1", db_name
            )
        finally:
            await admin_conn.close()

        assert exists is None

    @pytest.mark.asyncio
    async def test_database_test_case_utilities(self, test_db_with_tables):
        """Test DatabaseTestCase helper methods."""
        test_case = DatabaseTestCase(test_db_with_tables)

        # Test create_test_user
        user1 = await test_case.create_test_user()
        assert user1["id"] is not None
        assert "@example.com" in user1["email"]

        # Test with custom data
        user2 = await test_case.create_test_user(
            email="custom@test.com", full_name="Custom User", is_active=False
        )
        assert user2["email"] == "custom@test.com"
        assert user2["full_name"] == "Custom User"
        assert user2["is_active"] is False

        # Test count_rows
        user_count = await test_case.count_rows("users")
        assert user_count == 2

        # Test count with WHERE clause
        active_count = await test_case.count_rows("users", "is_active = true")
        assert active_count == 1

        # Test table_exists
        assert await test_case.table_exists("users")
        assert await test_case.table_exists("projects")
        assert not await test_case.table_exists("non_existent")

        # Test truncate_table
        await test_case.truncate_table("users", cascade=True)
        assert await test_case.count_rows("users") == 0

    @pytest.mark.asyncio
    async def test_fixture_test_db_factory(self, test_db_factory):
        """Test the test_db_factory fixture for multiple databases."""
        # Create multiple test databases
        db1 = await test_db_factory.create_db("app1", schema="app1_schema")
        db2 = await test_db_factory.create_db("app2", schema="app2_schema")
        db3 = await test_db_factory.create_db("shared")

        # Each database should be independent
        await db1.execute(
            """
            CREATE TABLE {{tables.config}} (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT
            )
        """
        )

        await db2.execute(
            """
            CREATE TABLE {{tables.config}} (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT,
                version INT DEFAULT 1
            )
        """
        )

        # Different schemas should have different table structures
        await db1.execute(
            "INSERT INTO {{tables.config}} (key, value) VALUES ($1, $2)",
            "app_name",
            "App 1",
        )

        await db2.execute(
            "INSERT INTO {{tables.config}} (key, value, version) VALUES ($1, $2, $3)",
            "app_name",
            "App 2",
            2,
        )

        # Verify isolation
        app1_data = await db1.fetch_one(
            "SELECT value FROM {{tables.config}} WHERE key = $1", "app_name"
        )
        app2_data = await db2.fetch_one(
            "SELECT value, version FROM {{tables.config}} WHERE key = $1", "app_name"
        )

        assert app1_data["value"] == "App 1"
        assert app2_data["value"] == "App 2"
        assert app2_data["version"] == 2

        # Shared database without schema
        await db3.execute("CREATE TABLE shared_data (id INT, data TEXT)")
        await db3.execute("INSERT INTO shared_data VALUES (1, 'shared')")

        shared = await db3.fetch_one("SELECT data FROM shared_data WHERE id = 1")
        assert shared["data"] == "shared"

    @pytest.mark.asyncio
    async def test_fixture_with_tables(self, test_db_with_tables):
        """Test the test_db_with_tables fixture."""
        # Verify tables exist but are empty
        tables = ["users", "projects", "agents"]

        for table in tables:
            assert await test_db_with_tables.table_exists(table)
            count = await test_db_with_tables.fetch_value(f"SELECT COUNT(*) FROM {table}")
            assert count == 0

        # Verify table relationships work
        user_id = await test_db_with_tables.execute_and_return_id(
            "INSERT INTO users (email, full_name) VALUES ($1, $2)",
            "test@example.com",
            "Test User",
        )

        project_id = await test_db_with_tables.execute_and_return_id(
            "INSERT INTO projects (name, owner_id) VALUES ($1, $2)",
            "Test Project",
            user_id,
        )

        task_id = await test_db_with_tables.execute_and_return_id(
            "INSERT INTO agents (project_id, title, assigned_to) VALUES ($1, $2, $3)",
            project_id,
            "Test Agent",
            user_id,
        )

        # Query with joins
        result = await test_db_with_tables.fetch_one(
            """
            SELECT
                t.title,
                p.name as project_name,
                u.email as assigned_to_email
            FROM agents t
            JOIN projects p ON t.project_id = p.id
            JOIN users u ON t.assigned_to = u.id
            WHERE t.id = $1
        """,
            task_id,
        )

        assert result["title"] == "Test Agent"
        assert result["project_name"] == "Test Project"
        assert result["assigned_to_email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_fixture_with_data(self, test_db_with_data):
        """Test the test_db_with_data fixture."""
        # Verify sample data is present
        users = await test_db_with_data.fetch_all("SELECT * FROM users ORDER BY email")
        assert len(users) == 3
        assert users[0]["email"] == "alice@example.com"
        assert users[1]["email"] == "bob@example.com"
        assert users[2]["email"] == "charlie@example.com"

        # Verify projects
        projects = await test_db_with_data.fetch_all("SELECT * FROM projects ORDER BY name")
        assert len(projects) == 2
        assert all(p["owner_id"] == users[0]["id"] for p in projects)

        # Verify agents
        agents = await test_db_with_data.fetch_all("SELECT * FROM agents ORDER BY id")
        assert len(agents) == 5

        # Test complex query on sample data
        task_summary = await test_db_with_data.fetch_all(
            """
            SELECT
                p.name as project,
                COUNT(t.id) as task_count,
                SUM(CASE WHEN t.status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN t.status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN t.status = 'pending' THEN 1 ELSE 0 END) as pending
            FROM projects p
            LEFT JOIN agents t ON p.id = t.project_id
            GROUP BY p.id, p.name
            ORDER BY p.name
        """
        )

        assert len(task_summary) == 2
        assert task_summary[0]["task_count"] == 3
        assert task_summary[1]["task_count"] == 2

    @pytest.mark.asyncio
    async def test_load_fixtures_from_files(self, test_db):
        """Test loading fixtures from SQL and JSON files."""
        test_database = AsyncTestDatabase(DatabaseTestConfig())

        with tempfile.TemporaryDirectory() as tmpdir:
            fixtures_dir = Path(tmpdir)

            # Create SQL fixture
            sql_fixture = fixtures_dir / "01_schema.sql"
            sql_fixture.write_text(
                """
                CREATE TABLE countries (
                    code VARCHAR(2) PRIMARY KEY,
                    name VARCHAR(100) NOT NULL
                );

                INSERT INTO countries (code, name) VALUES
                ('US', 'United States'),
                ('UK', 'United Kingdom'),
                ('JP', 'Japan');
            """
            )

            # Create JSON fixture
            json_fixture = fixtures_dir / "02_data.json"
            json_data = {
                "users": [
                    {"email": "admin@example.com", "full_name": "Admin User"},
                    {"email": "user1@example.com", "full_name": "User One"},
                    {"email": "user2@example.com", "full_name": "User Two"},
                ]
            }
            json_fixture.write_text(json.dumps(json_data))

            # Create tables first
            await test_db.execute(
                """
                CREATE TABLE users (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE,
                    full_name VARCHAR(255)
                )
            """
            )

            # Load fixtures
            loaded = await test_database.load_fixtures(test_db, fixtures_dir)

            assert "01_schema" in loaded
            assert loaded["users"] == 3

            # Verify data was loaded
            countries = await test_db.fetch_all("SELECT * FROM countries ORDER BY code")
            assert len(countries) == 3
            assert countries[0]["code"] == "JP"

            users = await test_db.fetch_all("SELECT * FROM users ORDER BY email")
            assert len(users) == 3
            assert users[0]["email"] == "admin@example.com"

    @pytest.mark.asyncio
    async def test_snapshot_and_comparison(self, test_db):
        """Test table snapshot functionality for testing."""
        test_database = AsyncTestDatabase(DatabaseTestConfig())

        # Create test table
        await test_db.execute(
            """
            CREATE TABLE inventory (
                id SERIAL PRIMARY KEY,
                item VARCHAR(100),
                quantity INT
            )
        """
        )

        # Insert initial data
        await test_db.execute(
            """
            INSERT INTO inventory (item, quantity) VALUES
            ('Widget', 100),
            ('Gadget', 50),
            ('Gizmo', 75)
        """
        )

        # Take snapshot
        snapshot_before = await test_database.snapshot_table(test_db, "inventory", order_by="item")

        # Perform some operation that shouldn't change data
        await test_db.fetch_all("SELECT * FROM inventory WHERE quantity > 60")

        # Verify unchanged
        await test_database.assert_table_unchanged(
            test_db, "inventory", snapshot_before, order_by="item"
        )

        # Now change data
        await test_db.execute("UPDATE inventory SET quantity = quantity - 10 WHERE item = 'Widget'")

        # Should raise assertion error
        with pytest.raises(AssertionError) as exc_info:
            await test_database.assert_table_unchanged(
                test_db, "inventory", snapshot_before, order_by="item"
            )

        assert "Table 'inventory' has changed" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_transaction_isolation_fixture(self, test_db_isolated):
        """Test the test_db_isolated fixture for transaction isolation."""
        # Create table
        await test_db_isolated.execute(
            """
            CREATE TABLE test_isolation (
                id INT PRIMARY KEY,
                value TEXT
            )
        """
        )

        # Insert data - this will be rolled back
        await test_db_isolated.execute("INSERT INTO test_isolation VALUES (1, 'test')")

        # Verify data exists within the test
        result = await test_db_isolated.fetch_one("SELECT * FROM test_isolation WHERE id = 1")
        assert result["value"] == "test"

        # Note: The fixture will rollback changes after the test
        # In a real test scenario, subsequent tests would see an empty table

    @pytest.mark.asyncio
    async def test_schema_specific_fixtures(self, test_db_with_schema):
        """Test fixtures with schema isolation."""
        # test_db_with_schema uses "test_schema"

        # Create table with schema placeholder
        await test_db_with_schema.execute(
            """
            CREATE TABLE {{tables.test_data}} (
                id SERIAL PRIMARY KEY,
                data JSONB
            )
        """
        )

        # Insert data
        test_data = {"type": "test", "schema": "isolated"}
        await test_db_with_schema.execute(
            "INSERT INTO {{tables.test_data}} (data) VALUES ($1)", json.dumps(test_data)
        )

        # Verify data is in correct schema
        result = await test_db_with_schema.fetch_one(
            """
            SELECT
                t.data,
                ns.nspname as schema_name
            FROM test_schema.test_data t
            JOIN pg_class c ON c.relname = 'test_data'
            JOIN pg_namespace ns ON c.relnamespace = ns.oid
            WHERE ns.nspname = 'test_schema'
        """
        )

        assert result["schema_name"] == "test_schema"

        # Parse data if it's a string (JSONB handling varies)
        data = result["data"]
        if isinstance(data, str):
            data = json.loads(data)
        assert data["type"] == "test"
