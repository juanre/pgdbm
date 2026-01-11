# Copyright (c) 2025 Juan Reyero
# Licensed under the MIT License

"""
Integration tests for database migration features.

These tests demonstrate how to use the migration system in real applications.
"""

import asyncio
import os
import tempfile
from pathlib import Path

import pytest

from pgdbm import AsyncMigrationManager, Migration, MigrationError


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
    async def test_migration_lock_serializes_apply(self, test_db, tmp_path):
        """Ensure advisory lock blocks concurrent migration application."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()

        migration_content = """
        SELECT pg_sleep(0.2);
        CREATE TABLE lock_test (id INT);
        """
        (migrations_dir / "001_lock_test.sql").write_text(migration_content)

        manager1 = AsyncMigrationManager(
            test_db, migrations_path=str(migrations_dir), module_name="lock_test"
        )
        manager2 = AsyncMigrationManager(
            test_db, migrations_path=str(migrations_dir), module_name="lock_test"
        )

        first_apply_started = asyncio.Event()
        second_apply_started = asyncio.Event()

        original_apply1 = manager1._apply_migration_on

        async def wrapped_apply1(conn, migration):
            first_apply_started.set()
            return await original_apply1(conn, migration)

        manager1._apply_migration_on = wrapped_apply1  # type: ignore[assignment]

        original_apply2 = manager2._apply_migration_on

        async def wrapped_apply2(conn, migration):
            second_apply_started.set()
            return await original_apply2(conn, migration)

        manager2._apply_migration_on = wrapped_apply2  # type: ignore[assignment]

        task1 = asyncio.create_task(manager1.apply_pending_migrations())
        await asyncio.wait_for(first_apply_started.wait(), timeout=1)

        task2 = asyncio.create_task(manager2.apply_pending_migrations())

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(second_apply_started.wait(), timeout=0.05)

        result1 = await task1
        result2 = await task2

        assert result1["status"] == "success"
        assert result2["status"] == "up_to_date"

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

    @pytest.mark.asyncio
    async def test_no_transaction_detection(self, test_db):
        """Test _requires_no_transaction detection."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manager = AsyncMigrationManager(test_db, migrations_path=tmpdir, module_name="test")

            # Should detect magic comment at start of file
            assert manager._requires_no_transaction(
                "-- pgdbm:no-transaction\nCREATE INDEX CONCURRENTLY ..."
            )
            # Should detect magic comment at start of any line
            assert manager._requires_no_transaction(
                "-- Description\n-- pgdbm:no-transaction\nCREATE INDEX ..."
            )

            # Should not detect without magic comment
            assert not manager._requires_no_transaction("CREATE TABLE test (id INT);")
            assert not manager._requires_no_transaction(
                "-- Some comment\nCREATE INDEX idx ON table(col);"
            )

            # Should NOT detect when magic comment is mentioned in text (not at line start)
            assert not manager._requires_no_transaction(
                "CREATE TABLE t (id INT);\n"
                "-- Note: we considered pgdbm:no-transaction but decided against it"
            )
            assert not manager._requires_no_transaction(
                "-- Comment about pgdbm:no-transaction feature\nCREATE TABLE t (id INT);"
            )
            # Should NOT detect if embedded in a string or other context
            assert not manager._requires_no_transaction(
                "INSERT INTO docs VALUES ('Use -- pgdbm:no-transaction for concurrent indexes');"
            )

            # Should NOT detect invalid suffix variations (word boundary check)
            assert not manager._requires_no_transaction(
                "-- pgdbm:no-transactional\nCREATE INDEX..."
            )
            assert not manager._requires_no_transaction(
                "-- pgdbm:no-transaction-mode\nCREATE INDEX..."
            )
            assert not manager._requires_no_transaction("-- pgdbm:no-transactions\nCREATE INDEX...")

    @pytest.mark.asyncio
    async def test_no_transaction_migration(self, test_db):
        """Test migration with pgdbm:no-transaction executes without transaction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            migrations = AsyncMigrationManager(
                test_db, migrations_path=tmpdir, module_name="no_tx_test"
            )

            # First, create a table in a regular migration
            (Path(tmpdir) / "001_create_table.sql").write_text(
                """
                CREATE TABLE no_tx_test (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255)
                );
                """
            )

            # Then create an index CONCURRENTLY in a no-transaction migration
            (Path(tmpdir) / "002_create_index_concurrently.sql").write_text(
                """
-- pgdbm:no-transaction
-- This migration creates an index concurrently, which requires autocommit mode.

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_no_tx_test_email
    ON no_tx_test (email);
                """
            )

            # Apply migrations
            result = await migrations.apply_pending_migrations()
            assert result["status"] == "success"
            assert len(result["applied"]) == 2
            assert result["applied"][0]["filename"] == "001_create_table.sql"
            assert result["applied"][1]["filename"] == "002_create_index_concurrently.sql"

            # Verify table was created
            assert await test_db.table_exists("no_tx_test")

            # Verify index was created
            indexes = await test_db.fetch_all(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'no_tx_test'
                """
            )
            index_names = [row["indexname"] for row in indexes]
            assert "idx_no_tx_test_email" in index_names

            # Verify migration was recorded
            history = await migrations.get_migration_history()
            applied_files = [h["filename"] for h in history]
            assert "002_create_index_concurrently.sql" in applied_files

    @pytest.mark.asyncio
    async def test_no_transaction_migration_error_handling(self, test_db):
        """Test error handling in no-transaction migrations.

        No-transaction migrations should properly report errors and not
        record failed migrations as applied.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            migrations = AsyncMigrationManager(
                test_db, migrations_path=tmpdir, module_name="no_tx_fail_test"
            )

            # Create a no-transaction migration with a syntax error
            (Path(tmpdir) / "001_failing.sql").write_text(
                """
-- pgdbm:no-transaction
-- This migration has a syntax error
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_nonexistent
    ON nonexistent_table (col,);
                """
            )

            # Apply migration - should fail
            result = await migrations.apply_pending_migrations()
            assert result["status"] == "error"
            assert "001_failing.sql" in result["failed_migration"]

            # Migration was NOT recorded as applied
            history = await migrations.get_migration_history()
            applied_files = [h["filename"] for h in history]
            assert "001_failing.sql" not in applied_files

    @pytest.mark.asyncio
    async def test_apply_migration_public_api_no_transaction(self, test_db):
        """Test apply_migration() public API supports no-transaction mode.

        The public apply_migration() method should handle no-transaction migrations
        the same way apply_pending_migrations() does.
        """
        with tempfile.TemporaryDirectory() as tmpdir:
            migrations = AsyncMigrationManager(
                test_db, migrations_path=tmpdir, module_name="apply_single_no_tx"
            )

            # Ensure migrations table exists
            await migrations.ensure_migrations_table()

            # First create the table via regular migration
            table_migration = Migration(
                filename="001_create_table.sql",
                checksum="abc123",
                content="""
                CREATE TABLE apply_single_no_tx (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255)
                );
                """,
            )
            await migrations.apply_migration(table_migration)
            assert await test_db.table_exists("apply_single_no_tx")

            # Now apply a no-transaction migration via the public API
            index_migration = Migration(
                filename="002_create_index.sql",
                checksum="def456",
                content="""-- pgdbm:no-transaction
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_apply_single_name
    ON apply_single_no_tx (name);
                """,
            )
            execution_time = await migrations.apply_migration(index_migration)
            assert execution_time > 0

            # Verify index was created
            indexes = await test_db.fetch_all(
                """
                SELECT indexname FROM pg_indexes
                WHERE tablename = 'apply_single_no_tx'
                """
            )
            index_names = [row["indexname"] for row in indexes]
            assert "idx_apply_single_name" in index_names


class TestSqlStatementSplitting:
    """Unit tests for _split_sql_statements helper function."""

    def test_basic_split(self):
        """Test basic statement splitting on semicolons."""
        from pgdbm.migrations import _split_sql_statements

        sql = "SELECT 1; SELECT 2; SELECT 3;"
        result = _split_sql_statements(sql)
        assert len(result) == 3
        assert result[0] == "SELECT 1;"
        assert result[1] == "SELECT 2;"
        assert result[2] == "SELECT 3;"

    def test_multiline_statements(self):
        """Test splitting multiline statements."""
        from pgdbm.migrations import _split_sql_statements

        sql = """
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name TEXT
);

CREATE TABLE posts (
    id SERIAL PRIMARY KEY,
    user_id INT
);
        """
        result = _split_sql_statements(sql)
        assert len(result) == 2
        assert "CREATE TABLE users" in result[0]
        assert "CREATE TABLE posts" in result[1]

    def test_single_quoted_strings_with_semicolons(self):
        """Test that semicolons in single-quoted strings are not split."""
        from pgdbm.migrations import _split_sql_statements

        sql = "INSERT INTO t VALUES ('hello; world'); SELECT 1;"
        result = _split_sql_statements(sql)
        assert len(result) == 2
        assert "hello; world" in result[0]

    def test_escaped_quotes(self):
        """Test handling of escaped single quotes ('')."""
        from pgdbm.migrations import _split_sql_statements

        sql = "INSERT INTO t VALUES ('it''s a test; really'); SELECT 2;"
        result = _split_sql_statements(sql)
        assert len(result) == 2
        assert "it''s a test; really" in result[0]

    def test_dollar_quoted_strings(self):
        """Test that semicolons in dollar-quoted strings are not split."""
        from pgdbm.migrations import _split_sql_statements

        sql = """
CREATE FUNCTION test() RETURNS void AS $$
BEGIN
    RAISE NOTICE 'test; with semicolon';
END;
$$ LANGUAGE plpgsql;

SELECT 1;
        """
        result = _split_sql_statements(sql)
        assert len(result) == 2
        assert "test; with semicolon" in result[0]
        assert "SELECT 1;" in result[1]

    def test_tagged_dollar_quotes(self):
        """Test that tagged dollar quotes ($tag$...$tag$) work correctly."""
        from pgdbm.migrations import _split_sql_statements

        sql = """
CREATE FUNCTION test() RETURNS void AS $body$
BEGIN
    RAISE NOTICE 'test; with semicolon';
    PERFORM $nested$SELECT 1; SELECT 2;$nested$;
END;
$body$ LANGUAGE plpgsql;

SELECT 3;
        """
        result = _split_sql_statements(sql)
        assert len(result) == 2

    def test_single_line_comments(self):
        """Test that semicolons in single-line comments are not split."""
        from pgdbm.migrations import _split_sql_statements

        sql = """
SELECT 1; -- this is a comment; with semicolon
SELECT 2;
        """
        result = _split_sql_statements(sql)
        assert len(result) == 2

    def test_block_comments(self):
        """Test that semicolons in block comments are not split."""
        from pgdbm.migrations import _split_sql_statements

        sql = """
SELECT 1; /* this is a
multiline comment; with semicolon
and more */
SELECT 2;
        """
        result = _split_sql_statements(sql)
        assert len(result) == 2

    def test_no_trailing_semicolon(self):
        """Test handling of statements without trailing semicolon."""
        from pgdbm.migrations import _split_sql_statements

        sql = "SELECT 1; SELECT 2"
        result = _split_sql_statements(sql)
        assert len(result) == 2
        assert result[0] == "SELECT 1;"
        assert result[1] == "SELECT 2"

    def test_empty_statements(self):
        """Test that empty statements are filtered out."""
        from pgdbm.migrations import _split_sql_statements

        sql = "SELECT 1;  ;  ; SELECT 2;"
        result = _split_sql_statements(sql)
        assert len(result) == 2

    def test_real_migration_content(self):
        """Test with realistic migration content similar to CREATE INDEX CONCURRENTLY."""
        from pgdbm.migrations import _split_sql_statements

        sql = """
-- pgdbm:no-transaction
-- Description: Add indexes for search

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_title_trgm
    ON beads.issues USING gin (title gin_trgm_ops);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_bead_id_trgm
    ON beads.issues USING gin (bead_id gin_trgm_ops);
        """
        result = _split_sql_statements(sql)
        assert len(result) == 3
        assert "CREATE EXTENSION" in result[0]
        assert "idx_title_trgm" in result[1]
        assert "idx_bead_id_trgm" in result[2]
