"""
Tests for async migration management.
"""

import os
import tempfile
from pathlib import Path

import pytest

from pgdbm import AsyncMigrationManager, Migration


@pytest.fixture
async def migration_dir():
    """Create a temporary directory for migration files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
async def migration_manager(test_db_manager, migration_dir):
    """Create a migration manager for testing."""
    return AsyncMigrationManager(
        test_db_manager, migrations_path=str(migration_dir), module_name="test_module"
    )


@pytest.mark.integration
async def test_migration_table_creation(test_db_manager, migration_manager):
    """Test that migration tracking table is created."""
    # Ensure table doesn't exist yet
    exists = await test_db_manager.table_exists("schema_migrations")
    assert exists is False

    # Create migrations table
    await migration_manager.ensure_migrations_table()

    # Verify table exists
    exists = await test_db_manager.table_exists("schema_migrations")
    assert exists is True

    # Verify table structure
    columns = await test_db_manager.fetch_all(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'schema_migrations'
        ORDER BY ordinal_position
    """
    )

    expected_columns = {
        "id": "integer",
        "filename": "character varying",
        "checksum": "character varying",
        "module_name": "character varying",
        "applied_at": "timestamp without time zone",
        "applied_by": "character varying",
        "execution_time_ms": "integer",
    }

    for col in columns:
        assert col["column_name"] in expected_columns
        assert expected_columns[col["column_name"]] == col["data_type"]


@pytest.mark.integration
async def test_migration_file_discovery(migration_manager, migration_dir):
    """Test finding migration files."""
    # Create some migration files
    migration1 = migration_dir / "001_create_users.sql"
    migration1.write_text(
        """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) NOT NULL
        );
    """
    )

    migration2 = migration_dir / "002_add_projects.sql"
    migration2.write_text(
        """
        CREATE TABLE projects (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL
        );
    """
    )

    # Hidden file should be ignored
    hidden = migration_dir / ".hidden.sql"
    hidden.write_text("SELECT 1;")

    # Non-SQL file should be ignored
    other = migration_dir / "readme.txt"
    other.write_text("This is not a migration")

    # Find migrations
    migrations = await migration_manager.find_migration_files()

    assert len(migrations) == 2
    assert migrations[0].filename == "001_create_users.sql"
    assert migrations[1].filename == "002_add_projects.sql"

    # Check checksums are calculated
    for migration in migrations:
        assert migration.checksum is not None
        assert len(migration.checksum) == 64  # SHA256 hex length


@pytest.mark.integration
async def test_apply_single_migration(test_db_manager, migration_manager, migration_dir):
    """Test applying a single migration."""
    # Create migration file
    migration_file = migration_dir / "001_create_test_table.sql"
    migration_content = """
        CREATE TABLE test_migration (
            id SERIAL PRIMARY KEY,
            value TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """
    migration_file.write_text(migration_content)

    # Create migration object
    migration = Migration(
        filename="001_create_test_table.sql",
        checksum=migration_manager._calculate_checksum(migration_content),
        content=migration_content,
    )

    # Apply migration
    await migration_manager.ensure_migrations_table()
    execution_time = await migration_manager.apply_migration(migration)

    assert execution_time > 0

    # Verify table was created
    exists = await test_db_manager.table_exists("test_migration")
    assert exists is True

    # Verify migration was recorded
    applied = await migration_manager.get_applied_migrations()
    assert "001_create_test_table.sql" in applied
    assert applied["001_create_test_table.sql"].checksum == migration.checksum


@pytest.mark.integration
async def test_apply_pending_migrations(test_db_manager, migration_manager, migration_dir):
    """Test applying all pending migrations."""
    # Create migration files
    migrations = [
        ("001_users.sql", "CREATE TABLE users (id SERIAL PRIMARY KEY);"),
        ("002_projects.sql", "CREATE TABLE projects (id SERIAL PRIMARY KEY);"),
        ("003_tasks.sql", "CREATE TABLE agents (id SERIAL PRIMARY KEY);"),
    ]

    for filename, content in migrations:
        (migration_dir / filename).write_text(content)

    # Apply all migrations
    result = await migration_manager.apply_pending_migrations()

    assert result["status"] == "success"
    assert len(result["applied"]) == 3
    assert result["total"] == 3

    # Verify all tables exist
    for table in ["users", "projects", "agents"]:
        exists = await test_db_manager.table_exists(table)
        assert exists is True

    # Run again - should skip all
    result = await migration_manager.apply_pending_migrations()
    assert result["status"] == "up_to_date"
    assert len(result["applied"]) == 0
    assert len(result["skipped"]) == 3


@pytest.mark.integration
async def test_migration_error_handling(test_db_manager, migration_manager, migration_dir):
    """Test migration error handling."""
    # Create migrations with an error in the middle
    migrations = [
        ("001_good.sql", "CREATE TABLE good1 (id INT);"),
        ("002_bad.sql", "CREATE TABLE ),*&^%$ bad syntax error;"),  # Very invalid SQL
        ("003_good.sql", "CREATE TABLE good2 (id INT);"),
    ]

    for filename, content in migrations:
        (migration_dir / filename).write_text(content)

    # Apply migrations - should fail on second
    result = await migration_manager.apply_pending_migrations()

    assert result["status"] == "error"
    assert result["failed_migration"] == "002_bad.sql"
    assert len(result["applied"]) == 1  # First one succeeded

    # Verify first table exists, others don't
    assert await test_db_manager.table_exists("good1") is True
    assert await test_db_manager.table_exists("good2") is False


@pytest.mark.integration
async def test_migration_history(test_db_manager, migration_manager, migration_dir):
    """Test migration history retrieval."""
    # Apply some migrations
    migrations = [
        ("001_first.sql", "CREATE TABLE first (id INT);"),
        ("002_second.sql", "CREATE TABLE second (id INT);"),
    ]

    for filename, content in migrations:
        (migration_dir / filename).write_text(content)

    await migration_manager.apply_pending_migrations()

    # Get history
    history = await migration_manager.get_migration_history(limit=10)

    assert len(history) == 2
    # History is ordered by applied_at DESC
    assert history[0]["filename"] == "002_second.sql"
    assert history[1]["filename"] == "001_first.sql"

    # Check fields
    for record in history:
        assert "filename" in record
        assert "module_name" in record
        assert "applied_at" in record
        assert "execution_time_ms" in record
        assert record["module_name"] == "test_module"


@pytest.mark.integration
async def test_create_migration(migration_manager, migration_dir):
    """Test creating new migration files."""
    # Create a migration
    content = "CREATE TABLE generated (id SERIAL PRIMARY KEY);"
    filepath = await migration_manager.create_migration(
        "add_generated_table", content, auto_transaction=False
    )

    # Verify file was created
    assert os.path.exists(filepath)
    path = Path(filepath)
    # Compare resolved paths to handle symlinks
    assert path.parent.resolve() == migration_dir.resolve()
    assert "add_generated_table" in path.name
    assert path.suffix == ".sql"

    # Verify content
    saved_content = path.read_text()
    assert saved_content == content

    # Test with auto transaction
    filepath2 = await migration_manager.create_migration(
        "with_transaction", "CREATE TABLE test (id INT);", auto_transaction=True
    )

    saved_content2 = Path(filepath2).read_text()
    assert "BEGIN;" in saved_content2
    assert "COMMIT;" in saved_content2


@pytest.mark.integration
async def test_rollback_migration_record(test_db_manager, migration_manager, migration_dir):
    """Test rolling back a migration record (for development)."""
    # Apply a migration
    migration_file = migration_dir / "001_test.sql"
    migration_file.write_text("CREATE TABLE test_rollback (id INT);")

    await migration_manager.apply_pending_migrations()

    # Verify it's applied
    applied = await migration_manager.get_applied_migrations()
    assert "001_test.sql" in applied

    # Rollback the record (not the changes)
    await migration_manager.rollback_migration("001_test.sql")

    # Verify record is gone
    applied = await migration_manager.get_applied_migrations()
    assert "001_test.sql" not in applied

    # But table still exists
    assert await test_db_manager.table_exists("test_rollback") is True

    # Can apply again
    result = await migration_manager.apply_pending_migrations()
    assert result["status"] == "error"  # Because table already exists
