# Testing Guide

This guide covers testing patterns for database-driven applications using pgdbm.

## Overview

The library provides:
- Automatic test database creation/cleanup
- Pytest fixtures for common scenarios
- Transaction isolation for tests
- Performance tracking
- Schema and data fixtures

## Basic Test Setup

### Install Test Dependencies

```bash
pip install pgdbm
pip install pytest pytest-asyncio

# Optional: install CLI extras if you use the `pgdbm` command
pip install "pgdbm[cli]"
```

### Configure pytest

```ini
# pytest.ini
[tool:pytest]
asyncio_mode = auto
testpaths = tests
```

### Using Test Fixtures

```python
# tests/conftest.py
import pytest
from pgdbm.fixtures.conftest import *  # Import all test fixtures

# Your custom fixtures can go here
```

## Available Fixtures

### test_db

Basic test database for each test:

```python
async def test_user_creation(test_db):
    # Fresh database for this test
    await test_db.execute("""
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE
        )
    """)

    user_id = await test_db.execute_and_return_id(
        "INSERT INTO users (email) VALUES ($1)",
        "test@example.com"
    )

    assert user_id == 1
    # Database automatically cleaned up
```

### test_db_with_schema

Test database with schema isolation:

```python
async def test_schema_isolation(test_db_with_schema):
    # Database has a test schema configured
    await test_db_with_schema.execute("""
        CREATE TABLE {{tables.users}} (
            id SERIAL PRIMARY KEY
        )
    """)

    # Table created in test schema
    exists = await test_db_with_schema.table_exists("users")
    assert exists
```

### test_db_with_tables

Pre-created common tables:

```python
async def test_with_tables(test_db_with_tables):
    # Tables already exist: users, projects, agents
    users = await test_db_with_tables.fetch_all(
        "SELECT * FROM users"
    )
    assert len(users) == 0  # Empty but tables exist
```

### test_db_with_data

Tables with sample data:

```python
async def test_with_sample_data(test_db_with_data):
    # Has users, projects, agents with sample data
    users = await test_db_with_data.fetch_all(
        "SELECT * FROM users ORDER BY id"
    )
    assert len(users) == 3
    assert users[0]['email'] == 'alice@example.com'
```

### test_db_isolated

Fast rollback-focused testing using a single database:

```python
async def test_transactional_fixture(test_db_isolated):
    # test_db_isolated is a TransactionManager with the same API as AsyncDatabaseManager
    # Create table (this will also be rolled back)
    await test_db_isolated.execute(
        "CREATE TABLE users (id SERIAL PRIMARY KEY, email TEXT)"
    )

    # Insert data
    await test_db_isolated.execute(
        "INSERT INTO users (email) VALUES ($1)",
        "transient@example.com"
    )

    # The row is visible inside the transaction
    user = await test_db_isolated.fetch_one(
        "SELECT * FROM users WHERE email = $1",
        "transient@example.com"
    )
    assert user is not None
    # All changes (including table creation) roll back when the fixture ends
```

Use this fixture for speed-sensitive suites where a per-test database would be too costly. It relies on savepoints managed by `TransactionManager`, which now correctly wraps the connection after the Oct 2025 bug fix.

## Writing Tests

### Basic CRUD Tests

```python
import pytest
from datetime import datetime

async def test_user_crud_operations(test_db_with_tables):
    # Create
    user_id = await test_db_with_tables.execute_and_return_id(
        """INSERT INTO users (email, full_name, created_at)
           VALUES ($1, $2, $3)""",
        "test@example.com", "Test User", datetime.utcnow()
    )

    # Read
    user = await test_db_with_tables.fetch_one(
        "SELECT * FROM users WHERE id = $1", user_id
    )
    assert user['email'] == 'test@example.com'

    # Update
    await test_db_with_tables.execute(
        "UPDATE users SET email = $1 WHERE id = $2",
        "newemail@example.com", user_id
    )

    # Verify update
    updated = await test_db_with_tables.fetch_one(
        "SELECT email FROM users WHERE id = $1", user_id
    )
    assert updated['email'] == 'newemail@example.com'

    # Delete
    await test_db_with_tables.execute(
        "DELETE FROM users WHERE id = $1", user_id
    )

    # Verify deletion
    deleted = await test_db_with_tables.fetch_one(
        "SELECT * FROM users WHERE id = $1", user_id
    )
    assert deleted is None
```

### Transaction Tests

```python
async def test_transaction_rollback(test_db_with_tables):
    initial_count = await test_db_with_tables.fetch_value(
        "SELECT COUNT(*) FROM users"
    )

    with pytest.raises(ValueError):
        async with test_db_with_tables.transaction():
            await test_db_with_tables.execute(
                "INSERT INTO users (email, full_name) VALUES ($1, $2)",
                "user1@example.com", "User One"
            )
            raise ValueError("Force rollback")

    # Verify rollback
    final_count = await test_db_with_tables.fetch_value(
        "SELECT COUNT(*) FROM users"
    )
    assert final_count == initial_count
```

### Testing with Fixtures

```python
@pytest.fixture
async def sample_user(test_db_with_tables):
    """Create a sample user for tests"""
    user_id = await test_db_with_tables.execute_and_return_id(
        "INSERT INTO users (email, full_name) VALUES ($1, $2)",
        "fixture@example.com", "Fixture User"
    )
    return user_id

async def test_user_projects(test_db_with_tables, sample_user):
    # Create project for user
    project_id = await test_db_with_tables.execute_and_return_id(
        "INSERT INTO projects (name, owner_id) VALUES ($1, $2)",
        "Test Project", sample_user
    )

    # Verify relationship
    projects = await test_db_with_tables.fetch_all(
        "SELECT * FROM projects WHERE owner_id = $1",
        sample_user
    )
    assert len(projects) == 1
```

## Testing Patterns

### Testing Services

```python
# app/services/user_service.py
class UserService:
    def __init__(self, db):
        self.db = db

    async def create_user(self, email: str, full_name: str):
        return await self.db.execute_and_return_id(
            "INSERT INTO users (email, full_name) VALUES ($1, $2)",
            email, full_name
        )

    async def get_user(self, user_id: int):
        return await self.db.fetch_one(
            "SELECT * FROM users WHERE id = $1", user_id
        )

# tests/test_user_service.py
from app.services.user_service import UserService

async def test_user_service(test_db_with_tables):
    service = UserService(test_db_with_tables)

    # Test creation
    user_id = await service.create_user("test@example.com", "Test User")
    assert user_id is not None

    # Test retrieval
    user = await service.get_user(user_id)
    assert user['email'] == "test@example.com"
```

### Testing Error Cases

```python
import asyncpg

async def test_unique_constraint(test_db_with_tables):
    # Insert first user
    await test_db_with_tables.execute(
        "INSERT INTO users (email, full_name) VALUES ($1, $2)",
        "dup@example.com", "Duplicate User"
    )

    # Try to insert duplicate email
    with pytest.raises(asyncpg.UniqueViolationError):
        await test_db_with_tables.execute(
            "INSERT INTO users (email, full_name) VALUES ($1, $2)",
            "dup@example.com", "Another User"  # Same email
        )
```

### Performance Testing

```python
import time

async def test_bulk_insert_performance(test_db_with_tables):
    start = time.time()

    # Prepare data
    users = [
        (f"user{i}@example.com", f"User {i}")
        for i in range(1000)
    ]

    # Bulk insert
    await test_db_with_tables.copy_records_to_table(
        "users",
        records=users,
        columns=['email', 'full_name']
    )

    elapsed = time.time() - start

    # Verify
    count = await test_db_with_tables.fetch_value(
        "SELECT COUNT(*) FROM users"
    )
    assert count == 1000
    assert elapsed < 1.0  # Should be fast
```

## Advanced Testing

### Custom Test Database Config

```python
# tests/conftest.py
import pytest_asyncio
from pgdbm.testing import AsyncTestDatabase, DatabaseTestConfig

@pytest_asyncio.fixture
async def custom_test_db():
    config = DatabaseTestConfig(
        host="localhost",
        port=5432,
        test_db_prefix="myapp_test_",  # Custom prefix
        test_db_template="template1",   # Different template
    )

    test_db = AsyncTestDatabase(config)
    await test_db.create_test_database()

    try:
        async with test_db.get_test_db_manager() as db:
            yield db
    finally:
        await test_db.drop_test_database()
```

### Testing Migrations

```python
from pgdbm import AsyncMigrationManager

async def test_migrations(test_db):
    migrations = AsyncMigrationManager(
        test_db,
        migrations_path="./migrations"
    )

    # Apply migrations
    results = await migrations.apply_pending_migrations()

    # Verify schema
    tables = await test_db.fetch_all("""
        SELECT tablename FROM pg_tables
        WHERE schemaname = 'public'
    """)

    table_names = {t['tablename'] for t in tables}
    assert 'users' in table_names
    assert 'migration_history' in table_names
```

### Testing with Multiple Schemas

```python
async def test_multi_tenant(test_db):
    # Create schemas
    await test_db.execute("CREATE SCHEMA tenant_1")
    await test_db.execute("CREATE SCHEMA tenant_2")

    # Create managers
    from pgdbm import AsyncDatabaseManager

    tenant1 = AsyncDatabaseManager(
        pool=test_db._pool,
        schema="tenant_1"
    )
    tenant2 = AsyncDatabaseManager(
        pool=test_db._pool,
        schema="tenant_2"
    )

    # Create same table in both schemas
    for tenant in [tenant1, tenant2]:
        await tenant.execute("""
            CREATE TABLE {{tables.data}} (
                id SERIAL PRIMARY KEY,
                value TEXT
            )
        """)

    # Insert different data
    await tenant1.execute(
        "INSERT INTO {{tables.data}} (value) VALUES ($1)",
        "Tenant 1 Data"
    )
    await tenant2.execute(
        "INSERT INTO {{tables.data}} (value) VALUES ($1)",
        "Tenant 2 Data"
    )

    # Verify isolation
    t1_data = await tenant1.fetch_one("SELECT * FROM {{tables.data}}")
    t2_data = await tenant2.fetch_one("SELECT * FROM {{tables.data}}")

    assert t1_data['value'] == "Tenant 1 Data"
    assert t2_data['value'] == "Tenant 2 Data"
```

## Best Practices

1. **Test Isolation**: Each test gets a fresh database
2. **Use Fixtures**: Leverage provided fixtures for common scenarios
3. **Test Transactions**: Verify both commit and rollback paths
4. **Test Constraints**: Ensure database constraints are working
5. **Performance Tests**: Include tests for bulk operations
6. **Error Testing**: Test error conditions and exceptions

## Common Mistakes and Anti-Patterns

This section documents real-world issues that cause test database leaks. These patterns were discovered in production codebases where thousands of orphaned `test_*` databases accumulated over time.

### Problem: Missing try/finally in Custom Fixtures

**WRONG** - Cleanup outside try/finally:

```python
@pytest_asyncio.fixture
async def test_db():
    test_database = AsyncTestDatabase(TEST_CONFIG)
    await test_database.create_test_database()

    async with test_database.get_test_db_manager(schema="myapp") as db:
        await db.execute('CREATE SCHEMA IF NOT EXISTS "myapp"')
        yield db

    await test_database.drop_test_database()  # ← NEVER RUNS IF TEST FAILS!
```

If the test fails or raises an exception, `drop_test_database()` is never called because it's outside a `try/finally` block.

**CORRECT** - Cleanup in finally block:

```python
@pytest_asyncio.fixture
async def test_db():
    test_database = AsyncTestDatabase(TEST_CONFIG)
    await test_database.create_test_database()

    try:
        async with test_database.get_test_db_manager(schema="myapp") as db:
            await db.execute('CREATE SCHEMA IF NOT EXISTS "myapp"')
            yield db
    finally:
        await test_database.drop_test_database()  # ← ALWAYS RUNS
```

### Problem: Manual Database Management in Test Functions

**WRONG** - Creating databases inside test functions:

```python
@pytest.mark.asyncio
async def test_something(redis_url):
    # Manual database management in every test = guaranteed leaks
    test_config = DatabaseTestConfig.from_env()
    test_db = AsyncTestDatabase(test_config)
    db_name = await test_db.create_test_database()

    try:
        database_url = f"postgresql://.../{db_name}"
        # ... test code ...
    finally:
        await test_db.drop_test_database()
```

This duplicates fixture logic in every test. If the test is interrupted (Ctrl+C), the finally block may not run. If setup fails after database creation, cleanup may be skipped.

**CORRECT** - Use fixtures:

```python
@pytest.mark.asyncio
async def test_something(db_infra, redis_client):
    # Fixtures handle creation and cleanup automatically
    # ... test code using db_infra ...
```

### Problem: Silent Cleanup Failures

**WRONG** - Swallowing cleanup exceptions:

```python
finally:
    try:
        asyncio.run(test_db.drop_test_database())
    except Exception:
        pass  # ← SILENTLY IGNORES FAILURE, DATABASE LEAKS
```

Or:

```python
except Exception as e:
    logger.warning(f"Failed to drop database: {e}")
    # ← LOGS BUT CONTINUES, DATABASE STILL EXISTS
```

**CORRECT** - Let cleanup failures propagate (or at least be visible):

```python
finally:
    await test_db.drop_test_database()  # ← Failure is visible
```

If cleanup must be best-effort, at least make failures loud:

```python
finally:
    try:
        await test_db.drop_test_database()
    except Exception as e:
        # Make it impossible to miss
        pytest.fail(f"CRITICAL: Test database cleanup failed: {e}")
```

### Problem: Session-Scoped Fixtures with Manual Event Loops

**WRONG** - Managing event loops manually in session fixtures:

```python
@pytest.fixture(scope="session")
def integration_server():
    # Create database in one event loop
    loop = asyncio.new_event_loop()
    test_db, db_name = loop.run_until_complete(_create_test_database())
    loop.close()

    # ... start server ...

    yield server_url

    # Cleanup in another event loop
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_drop_test_database(db_name))
    except Exception as e:
        logger.warning(f"Cleanup failed: {e}")  # ← SILENT FAILURE
    finally:
        loop.close()
```

This is fragile because:
- If the session is interrupted, cleanup never runs
- Multiple event loops can cause issues
- Silent exception handling hides failures

**BETTER** - Use pytest-asyncio's session-scoped fixtures when possible, or accept that session fixtures may leak on interruption.

### The Correct Pattern: Use Provided Fixtures

The pgdbm fixtures handle all cleanup automatically:

```python
# tests/conftest.py
pytest_plugins = ("pgdbm.fixtures.conftest",)

# Or import directly:
# from pgdbm.fixtures.conftest import *
```

Then use fixtures in your tests:

```python
async def test_basic(test_db):
    # test_db is automatically created and cleaned up
    await test_db.execute("SELECT 1")


async def test_with_factory(test_db_factory):
    # Factory creates multiple databases, all cleaned up
    db1 = await test_db_factory.create_db("first")
    db2 = await test_db_factory.create_db("second")
    # Both cleaned up automatically
```

### Application-Specific Fixtures

For applications that need custom infrastructure (like a `DatabaseInfra` class with multiple schemas), create a fixture that builds on pgdbm's fixtures:

**CORRECT** - Building on test_db_factory:

```python
# tests/conftest.py
pytest_plugins = ("pgdbm.fixtures.conftest",)

@pytest_asyncio.fixture
async def shared_test_pool(test_db_factory):
    """Create a shared pool using pgdbm's managed test database."""
    db_manager = await test_db_factory.create_db(suffix="myapp")

    config = DatabaseConfig(connection_string=db_manager.config.get_dsn())
    pool = await AsyncDatabaseManager.create_shared_pool(config)

    yield pool

    await pool.close()
    # test_db_factory handles database cleanup automatically


@pytest_asyncio.fixture
async def app_db(shared_test_pool):
    """Create application database managers using shared pool."""
    # Create schemas
    temp = AsyncDatabaseManager(pool=shared_test_pool, schema=None)
    await temp.execute("CREATE SCHEMA IF NOT EXISTS myapp")

    # Create schema-specific manager
    app_manager = AsyncDatabaseManager(pool=shared_test_pool, schema="myapp")

    # Apply migrations
    migrations = AsyncMigrationManager(
        app_manager,
        migrations_path="src/myapp/migrations",
        module_name="myapp",
    )
    await migrations.apply_pending_migrations()

    yield app_manager
    # shared_test_pool fixture handles pool cleanup
    # test_db_factory handles database cleanup
```

### CLI Tests That Need DATABASE_URL

For CLI tests that spawn subprocesses needing a real `DATABASE_URL`, you must manage databases manually. Use proper cleanup:

```python
class TestCLI:
    def test_cli_command(self):
        async def run_test():
            test_database = AsyncTestDatabase(TEST_CONFIG)
            await test_database.create_test_database()

            try:
                db_url = f"postgresql://.../{test_database._test_db_name}"

                async with test_database.get_test_db_manager(schema="myapp") as db:
                    # Setup
                    await db.execute('CREATE SCHEMA IF NOT EXISTS "myapp"')
                    # ... create test data ...

                    # Run CLI with DATABASE_URL
                    result = runner.invoke(cli, ["command"], env={"DATABASE_URL": db_url})
                    assert result.exit_code == 0

            finally:
                await test_database.drop_test_database()  # ← MUST be in finally

        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(run_test())
        finally:
            loop.close()
```

### Summary: Database Cleanup Checklist

1. **Use pgdbm fixtures** - Don't reinvent the wheel
2. **Custom fixtures need try/finally** - Cleanup code must be in a `finally` block
3. **Never swallow cleanup exceptions** - Make failures visible
4. **Don't duplicate fixture logic in tests** - Extract to fixtures
5. **Avoid manual event loop management** - Let pytest-asyncio handle it
6. **Test interruption behavior** - Run `pytest` and hit Ctrl+C; are databases cleaned up?

### Debugging Leftover Databases

If you suspect database leaks, check with:

```sql
SELECT datname FROM pg_database WHERE datname ~ '^test_[0-9a-f]{8}';
```

Clean them up with:

```sql
SELECT 'DROP DATABASE IF EXISTS "' || datname || '";'
FROM pg_database
WHERE datname ~ '^test_[0-9a-f]{8}';
```

Then fix your test patterns to prevent future leaks.

## Next Steps

- [API Reference](api-reference.md) - Complete method documentation
- [Patterns Guide](patterns.md) - Application integration patterns
