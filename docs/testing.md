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
pip install pgdbm[test]
# or
pip install pytest pytest-asyncio
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
import pytest
from pgdbm import AsyncTestDatabase, DatabaseTestConfig

@pytest.fixture
async def custom_test_db():
    config = DatabaseTestConfig(
        host="localhost",
        port=5432,
        test_db_prefix="myapp_test_",  # Custom prefix
        test_db_template="template1",   # Different template
    )

    test_db = AsyncTestDatabase(config)
    db_name = await test_db.create_test_database()

    async with test_db.get_test_db_manager() as db:
        yield db

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

## Next Steps

- [API Reference](api-reference.md) - Complete method documentation
- [Patterns Guide](patterns.md) - Application integration patterns
