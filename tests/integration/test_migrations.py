# Copyright (c) 2025 Juan Reyero
# Licensed under the MIT License

"""
Integration tests for database migration features.

These tests demonstrate how to use the migration system in real applications.
"""

import os
import tempfile
from pathlib import Path

import pytest

from pgdbm import AsyncMigrationManager, MigrationError


class TestMigrationManagement:
    """Test database migration features."""

    @pytest.mark.asyncio
    async def test_basic_migration_workflow(self, test_db):
        """Test basic migration creation and application."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Initialize migration manager
            migrations = AsyncMigrationManager(test_db, migrations_path=tmpdir)

            # Create migrations directory
            await migrations.ensure_migrations_table()

            # Create first migration
            migration_content = """
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX idx_users_email ON users(email);
            """

            # Write migration file
            migration_file = Path(tmpdir) / "001_create_users.sql"
            migration_file.write_text(migration_content)

            # Check pending migrations
            pending = await migrations.get_pending_migrations()
            assert len(pending) == 1
            assert pending[0].filename == "001_create_users.sql"
            assert pending[0].version == "001"

            # Apply migrations
            result = await migrations.apply_pending_migrations()
            assert result["status"] == "success"
            assert len(result["applied"]) == 1
            assert result["applied"][0]["filename"] == "001_create_users.sql"

            # Verify table was created
            assert await test_db.table_exists("users")

            # Check no more pending migrations
            pending_after = await migrations.get_pending_migrations()
            assert len(pending_after) == 0

            # Check migration history
            history = await migrations.get_migration_history()
            assert len(history) > 0
            assert history[0]["filename"] == "001_create_users.sql"

    @pytest.mark.asyncio
    async def test_migration_version_extraction(self, test_db):
        """Test different migration naming patterns."""
        with tempfile.TemporaryDirectory() as tmpdir:
            migrations = AsyncMigrationManager(test_db, migrations_path=tmpdir)

            # Test different naming patterns
            test_cases = [
                ("001_initial.sql", "001"),  # Numeric prefix
                ("002_add_table.sql", "002"),
                ("V1__create_schema.sql", "1"),  # Flyway style
                ("V2__add_index.sql", "2"),
                ("20240126120000_timestamp.sql", "20240126120000"),  # Timestamp
                ("20240127093015_another.sql", "20240127093015"),
                ("custom_name.sql", "custom_name"),  # No pattern
            ]

            # Create migration files
            for filename, _ in test_cases:
                content = f"-- Migration {filename}\nSELECT 1;"
                (Path(tmpdir) / filename).write_text(content)

            # Get all migrations and check versions
            all_migrations = await migrations.find_migration_files()

            # Sort by filename for consistent ordering
            all_migrations.sort(key=lambda m: m.filename)

            # Create a dict of expected versions by filename
            expected_versions = dict(test_cases)

            # Check each migration has the expected version
            for migration in all_migrations:
                assert migration.filename in expected_versions
                assert migration.version == expected_versions[migration.filename]

    @pytest.mark.asyncio
    async def test_migration_checksum_validation(self, test_db):
        """Test that modified migrations are detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            migrations = AsyncMigrationManager(test_db, migrations_path=tmpdir)

            # Create and apply a migration
            migration_file = Path(tmpdir) / "001_test.sql"
            migration_file.write_text("CREATE TABLE test1 (id INT);")

            await migrations.apply_pending_migrations()

            # Modify the migration file (this should be detected)
            migration_file.write_text("CREATE TABLE test1 (id INT, name TEXT);")

            # Try to check pending migrations - should raise error
            with pytest.raises(MigrationError) as exc_info:
                await migrations.get_pending_migrations()

            assert "has been modified after being applied" in str(exc_info.value)
            assert "001_test.sql" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_dry_run_migrations(self, test_db):
        """Test dry run functionality."""
        with tempfile.TemporaryDirectory() as tmpdir:
            migrations = AsyncMigrationManager(test_db, migrations_path=tmpdir)

            # Create multiple migrations
            for i in range(1, 4):
                content = f"CREATE TABLE table_{i} (id SERIAL PRIMARY KEY);"
                (Path(tmpdir) / f"00{i}_create_table_{i}.sql").write_text(content)

            # Dry run
            result = await migrations.apply_pending_migrations(dry_run=True)
            assert result["status"] == "dry_run"
            assert len(result["pending"]) == 3
            assert result["applied"] == []

            # Verify no tables were created
            for i in range(1, 4):
                assert not await test_db.table_exists(f"table_{i}")

            # Now apply for real
            result = await migrations.apply_pending_migrations()
            assert result["status"] == "success"
            assert len(result["applied"]) == 3

            # Verify tables were created
            for i in range(1, 4):
                assert await test_db.table_exists(f"table_{i}")

    @pytest.mark.asyncio
    async def test_migration_ordering(self, test_db):
        """Test that migrations are applied in correct order."""
        with tempfile.TemporaryDirectory() as tmpdir:
            migrations = AsyncMigrationManager(test_db, migrations_path=tmpdir)

            # Create migrations out of order
            migration_files = [
                (
                    "003_add_constraints.sql",
                    "ALTER TABLE users ADD CONSTRAINT check_age CHECK (age >= 0);",
                ),
                (
                    "001_create_users.sql",
                    "CREATE TABLE users (id SERIAL PRIMARY KEY, age INT);",
                ),
                (
                    "002_add_email.sql",
                    "ALTER TABLE users ADD COLUMN email VARCHAR(255);",
                ),
            ]

            for filename, content in migration_files:
                (Path(tmpdir) / filename).write_text(content)

            # Apply migrations
            result = await migrations.apply_pending_migrations()

            # Verify they were applied in correct order
            assert result["applied"][0]["filename"] == "001_create_users.sql"
            assert result["applied"][1]["filename"] == "002_add_email.sql"
            assert result["applied"][2]["filename"] == "003_add_constraints.sql"

            # Verify final schema is correct
            columns = await test_db.fetch_all(
                """
                SELECT column_name, data_type
                FROM information_schema.columns
                WHERE table_name = 'users'
                ORDER BY ordinal_position
            """
            )

            assert len(columns) == 3
            assert columns[1]["column_name"] == "age"
            assert columns[2]["column_name"] == "email"

    @pytest.mark.asyncio
    async def test_migration_with_placeholders(self, test_db_with_schema):
        """Test migrations with schema placeholders."""
        with tempfile.TemporaryDirectory() as tmpdir:
            migrations = AsyncMigrationManager(test_db_with_schema, migrations_path=tmpdir)

            # Ensure migrations table exists in the schema
            await migrations.ensure_migrations_table()

            # Create migration with placeholders
            migration_content = """
            CREATE TABLE {{tables.products}} (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                price DECIMAL(10, 2)
            );

            CREATE TABLE {{tables.categories}} (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL
            );

            CREATE TABLE {{tables.product_categories}} (
                product_id INT REFERENCES {{tables.products}}(id),
                category_id INT REFERENCES {{tables.categories}}(id),
                PRIMARY KEY (product_id, category_id)
            );
            """

            (Path(tmpdir) / "001_create_product_schema.sql").write_text(migration_content)

            # Apply migration
            await migrations.apply_pending_migrations()

            # Verify tables were created in correct schema
            tables = await test_db_with_schema.fetch_all(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = $1
                ORDER BY table_name
            """,
                "test_schema",
            )

            table_names = [t["table_name"] for t in tables]
            assert "products" in table_names
            assert "categories" in table_names
            assert "product_categories" in table_names

    @pytest.mark.asyncio
    async def test_failed_migration_rollback(self, test_db):
        """Test that failed migrations are rolled back."""
        with tempfile.TemporaryDirectory() as tmpdir:
            migrations = AsyncMigrationManager(test_db, migrations_path=tmpdir)

            # Create a migration that will fail
            migration_content = """
            CREATE TABLE test_table (id SERIAL PRIMARY KEY);
            INSERT INTO test_table (id) VALUES (1);
            -- This will fail due to syntax error
            CREATE TABLE another_table (id SERIAL PRIMARY KEY,);
            """

            (Path(tmpdir) / "001_failing_migration.sql").write_text(migration_content)

            # Try to apply migration
            result = await migrations.apply_pending_migrations()
            assert result["status"] == "error"
            assert "001_failing_migration.sql" in result["failed_migration"]

            # Verify the first table was NOT created (rolled back)
            assert not await test_db.table_exists("test_table")

            # Verify migration was not recorded as applied
            history = await migrations.get_migration_history()
            applied_files = [h["filename"] for h in history]
            assert "001_failing_migration.sql" not in applied_files

    @pytest.mark.asyncio
    async def test_module_specific_migrations(self, test_db):
        """Test module-specific migration tracking."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create migrations for different modules
            auth_dir = Path(tmpdir) / "auth"
            billing_dir = Path(tmpdir) / "billing"
            auth_dir.mkdir()
            billing_dir.mkdir()

            # Auth module migrations
            auth_migrations = AsyncMigrationManager(
                test_db, migrations_path=str(auth_dir), module_name="auth"
            )

            (auth_dir / "001_create_users.sql").write_text(
                """
                CREATE TABLE auth_users (
                    id SERIAL PRIMARY KEY,
                    username VARCHAR(100) UNIQUE NOT NULL,
                    password_hash VARCHAR(255) NOT NULL
                );
            """
            )

            # Billing module migrations
            billing_migrations = AsyncMigrationManager(
                test_db, migrations_path=str(billing_dir), module_name="billing"
            )

            (billing_dir / "001_create_subscriptions.sql").write_text(
                """
                CREATE TABLE subscriptions (
                    id SERIAL PRIMARY KEY,
                    user_id INT NOT NULL,
                    plan VARCHAR(50) NOT NULL,
                    expires_at TIMESTAMP
                );
            """
            )

            # Apply auth migrations
            auth_result = await auth_migrations.apply_pending_migrations()
            assert auth_result["status"] == "success"
            assert len(auth_result["applied"]) == 1

            # Apply billing migrations
            billing_result = await billing_migrations.apply_pending_migrations()
            assert billing_result["status"] == "success"
            assert len(billing_result["applied"]) == 1

            # Verify both tables exist
            assert await test_db.table_exists("auth_users")
            assert await test_db.table_exists("subscriptions")

            # Verify migrations are tracked separately
            auth_history = await auth_migrations.get_migration_history()
            billing_history = await billing_migrations.get_migration_history()

            assert len(auth_history) == 1
            assert auth_history[0]["module_name"] == "auth"

            assert len(billing_history) == 1
            assert billing_history[0]["module_name"] == "billing"

    @pytest.mark.asyncio
    async def test_migration_performance_tracking(self, test_db):
        """Test that migration execution time is tracked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            migrations = AsyncMigrationManager(test_db, migrations_path=tmpdir)

            # Create a migration with multiple operations
            migration_content = """
            CREATE TABLE large_table (
                id SERIAL PRIMARY KEY,
                data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Insert some data to make it take measurable time
            INSERT INTO large_table (data)
            SELECT 'Test data ' || generate_series(1, 1000);

            CREATE INDEX idx_large_table_created ON large_table(created_at);
            """

            (Path(tmpdir) / "001_performance_test.sql").write_text(migration_content)

            # Apply migration
            result = await migrations.apply_pending_migrations()

            # Check execution time was recorded
            assert result["applied"][0]["execution_time_ms"] > 0
            assert result["total_time_ms"] > 0

            # Check history includes execution time
            history = await migrations.get_migration_history()
            assert history[0]["execution_time_ms"] > 0

    @pytest.mark.asyncio
    async def test_create_migration_helper(self, test_db):
        """Test the create_migration helper method."""
        with tempfile.TemporaryDirectory() as tmpdir:
            migrations = AsyncMigrationManager(test_db, migrations_path=tmpdir)

            # Create a migration using the helper
            migration_sql = """
            CREATE TABLE generated_migration (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100)
            );
            """

            filepath = await migrations.create_migration(
                name="add_generated_table", content=migration_sql, auto_transaction=True
            )

            # Verify file was created
            assert os.path.exists(filepath)

            # Read the file content
            with open(filepath) as f:
                content = f.read()

            # Verify transaction wrapper was added
            assert "BEGIN;" in content
            assert "COMMIT;" in content
            assert "CREATE TABLE generated_migration" in content

            # Apply the migration
            result = await migrations.apply_pending_migrations()
            assert result["status"] == "success"

            # Verify table was created
            assert await test_db.table_exists("generated_migration")
