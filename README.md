# pgdbm

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/pgdbm.svg)](https://pypi.org/project/pgdbm/)
[![PyPI](https://img.shields.io/pypi/v/pgdbm.svg)](https://pypi.org/project/pgdbm/)

A PostgreSQL library for Python that provides high-level async database operations with built-in migration management, connection pooling, and testing utilities. It offers:

- **Connection pooling** with proper resource management
- **Schema migrations** that are version-controlled and automated
- **Testing utilities** that provide isolated test databases
- **Module isolation** when multiple services share a database
- **Monitoring** for slow queries and connection issues

## Key Features

- **🚀 High Performance** - Built on asyncpg, the fastest PostgreSQL driver for Python
- **📦 Migration System** - Version-controlled schema migrations with automatic ordering
- **🧪 Testing Support** - Fixtures and utilities for database testing
- **🔧 Module Isolation** - Prevent table conflicts when modules share databases
- **📊 Monitoring** - Track slow queries and connection pool metrics
- **🔒 Type Safe** - Full type hints and Pydantic integration

### Design intent: dual ownership

pgdbm is designed so a module can either:
- **Own its database** when run independently (it creates a pool and runs its own migrations), or
- **Use a database owned by another** component via a shared pool while still running its own migrations into a schema namespace.

This keeps modules portable: the same code can run as a standalone service or as part of a larger app.

## Installation

```bash
# Install using uv (recommended)
uv add pgdbm

# Or using pip
pip install pgdbm
```

## Quick Start

### 1. Create a migration file

```sql
-- migrations/001_initial.sql
CREATE TABLE IF NOT EXISTS {{tables.users}} (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### 2. Use pgdbm

```python
from pgdbm import AsyncDatabaseManager, DatabaseConfig, AsyncMigrationManager

# Configure and connect
config = DatabaseConfig(
    host="localhost",
    database="myapp",
    user="postgres",
    password="secret"
)

db = AsyncDatabaseManager(config)
await db.connect()

# Apply migrations
migrations = AsyncMigrationManager(db, migrations_path="./migrations")
await migrations.apply_pending()

# Use your database
user_id = await db.execute_and_return_id(
    "INSERT INTO {{tables.users}} (email) VALUES ($1)",
    "user@example.com"
)

# Clean up
await db.disconnect()
```

Standalone vs shared-pool usage:

```python
# Standalone (owns the DB):
config = DatabaseConfig(connection_string="postgresql://localhost/app", schema="users")
db = AsyncDatabaseManager(config)
await db.connect()
await AsyncMigrationManager(db, "./migrations", module_name="users").apply_pending()

# Shared pool (uses external DB):
shared = await AsyncDatabaseManager.create_shared_pool(DatabaseConfig(connection_string="postgresql://localhost/app"))
db = AsyncDatabaseManager(pool=shared, schema="users")  # Module still runs its own migrations
await AsyncMigrationManager(db, "./migrations", module_name="users").apply_pending()
```

## Core Patterns

### 1. Migration Management

pgdbm includes a built-in migration system:

```python
# Apply all pending migrations
migrations = AsyncMigrationManager(db, migrations_path="./migrations")
result = await migrations.apply_pending()

# Check what was applied
for migration in result['applied']:
    print(f"Applied {migration['filename']} in {migration['execution_time_ms']}ms")
```

Migrations are automatically ordered by version number extracted from filenames.

### 2. Module Isolation

When multiple modules share a database, use schemas to prevent table conflicts:

```python
# Each module can get its own schema
user_db = AsyncDatabaseManager(
    config=DatabaseConfig(database="app", schema="user_module")
)
blog_db = AsyncDatabaseManager(
    config=DatabaseConfig(database="app", schema="blog_module")
)

# Both can have a "users" table without conflict:
# - user_module.users
# - blog_module.users
```

The `{{tables.tablename}}` syntax in queries automatically expands to the correct schema-qualified name.

### 3. Connection Pool Sharing

For applications with multiple services sharing a database:

```python
# Create shared pool
shared_pool = await AsyncDatabaseManager.create_shared_pool(config)

# Each service gets its own schema but shares connections
user_db = AsyncDatabaseManager(pool=shared_pool, schema="users")
billing_db = AsyncDatabaseManager(pool=shared_pool, schema="billing")
```

### 4. Testing Support

Built-in fixtures for database tests:

```python
# conftest.py
from pgdbm.fixtures.conftest import *

# test_users.py
async def test_create_user(test_db):
    # Automatic test database with cleanup
    await test_db.execute("""
        CREATE TABLE users (id SERIAL PRIMARY KEY, email TEXT)
    """)

    user_id = await test_db.execute_and_return_id(
        "INSERT INTO users (email) VALUES ($1)",
        "test@example.com"
    )
    assert user_id == 1
```

### 5. Monitoring

Track database performance:

```python
from pgdbm import MonitoredAsyncDatabaseManager

db = MonitoredAsyncDatabaseManager(
    config=config,
    slow_query_threshold_ms=100  # Log queries over 100ms
)

# Get metrics
metrics = await db.get_query_metrics()
slow_queries = await db.get_slow_queries(limit=10)
```

### 6. Production TLS and Timeouts

Enable TLS with certificate verification and enforce server-side timeouts:

```python
from pgdbm import AsyncDatabaseManager, DatabaseConfig

config = DatabaseConfig(
    connection_string="postgresql://db.example.com/app",
    ssl_enabled=True,
    ssl_mode="verify-full",           # 'require' | 'verify-ca' | 'verify-full'
    ssl_ca_file="/etc/ssl/certs/ca.pem",
    # Optional mutual TLS:
    # ssl_cert_file="/etc/ssl/certs/client.crt",
    # ssl_key_file="/etc/ssl/private/client.key",

    # Sensible timeouts (ms)
    statement_timeout_ms=60_000,
    idle_in_transaction_session_timeout_ms=60_000,
    lock_timeout_ms=5_000,
)

db = AsyncDatabaseManager(config)
await db.connect()
```

Notes:
- Use `verify-full` for strict hostname and certificate validation in production.
- Timeouts are applied via `server_settings`; you can override or disable by passing None.

## Examples

The `examples/` directory contains applications:

- **todo-app/** - REST API with migrations, testing, and error handling
- **saas-app/** - Multi-tenant SaaS application
- **microservices/** - Multiple services sharing a connection pool

## Documentation

- [Quickstart Guide](docs/quickstart.md) - Get started
- [Patterns Guide](docs/patterns.md) - Deployment patterns, schema isolation, and framework integration
- [Migration Guide](docs/migrations.md) - Schema versioning and {{tables.}} syntax
- [API Reference](docs/api-reference.md) - Complete API documentation
- [Testing Guide](docs/testing.md) - Testing best practices

## Contributing

Short version:

- Requirements: Python 3.9+, PostgreSQL 12+, uv (or pip)
- Setup:
  - uv: `uv sync`
  - pip: `pip install -e ".[dev]"`
  - hooks: `pre-commit install`
- Run tests: `pytest`
- Lint/type-check: `pre-commit run --all-files`

Notes:

- Integration tests use ephemeral databases; you can override with env vars like `TEST_DB_HOST`, `TEST_DB_PORT`, `TEST_DB_USER`, `TEST_DB_PASSWORD`.
- Keep PRs small and focused, include tests/docs for user-visible changes.
- Style is enforced via Black/Isort/Ruff/Mypy; run pre-commit locally before pushing.

## License

MIT License - see [LICENSE](LICENSE) for details.
