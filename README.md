# pgdbm

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/pypi/pyversions/pgdbm.svg)](https://pypi.org/project/pgdbm/)
[![PyPI](https://img.shields.io/pypi/v/pgdbm.svg)](https://pypi.org/project/pgdbm/)

A PostgreSQL library for Python that provides high-level async database operations with built-in migration management, connection pooling, and testing utilities.

## Quick Architecture Decision

**Choose your pattern based on your needs:**

| If you have... | Use this pattern | See example |
|---------------|------------------|-------------|
| **Single service** | [Single Database Manager](#quick-start) | Quick Start below |
| **Multiple services** | [Shared Pool Pattern](#3-connection-pool-sharing) | [microservices/](examples/microservices/) |
| **Multi-tenant SaaS** | [Schema Isolation](#2-module-isolation) | [saas-app/](examples/saas-app/) |
| **Reusable library** | [Dual-Mode Pattern](#design-intent-dual-ownership) | [Pattern Guide](docs/production-patterns.md#dual-mode-library-pattern) |

> **New to pgdbm?** Start with our [Production Patterns Guide](docs/production-patterns.md) to avoid common pitfalls and learn best practices from real-world experience.

## Key Features

- **High Performance** - Built on asyncpg, the fastest PostgreSQL driver for Python
- **Migration System** - Version-controlled schema migrations with automatic ordering
- **Testing Support** - Fixtures and utilities for database testing
- **Module Isolation** - Prevent table conflicts when modules share databases
- **Monitoring** - Track slow queries and connection pool metrics
- **Type Safe** - Full type hints and Pydantic integration

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

# Install with CLI support (optional)
pip install pgdbm[cli]
```

## Claude Code Skills

pgdbm provides **expert guidance skills** for Claude Code that teach Claude how to work with the library effectively. When you use Claude Code with pgdbm, these skills automatically activate to provide:

- ✅ Production-ready code examples
- ✅ Best practices and patterns
- ✅ Common pitfalls to avoid
- ✅ Architecture guidance
- ✅ Testing strategies

**No manual needed** - just ask Claude naturally and the right skills load automatically!

### Installation

```bash
# In Claude Code terminal, add the marketplace
/plugin marketplace add juanre/ai-tools

# Install all pgdbm skills (recommended)
/plugin install pgdbm@juanre-ai-tools

# Or install individual skills
/plugin install pgdbm-shared-pool@juanre-ai-tools
/plugin install pgdbm-testing@juanre-ai-tools
```

### Available Skills

| Skill | Description | Install |
|-------|-------------|---------|
| `pgdbm` | All pgdbm skills (recommended) | `/plugin install pgdbm@juanre-ai-tools` |
| `pgdbm-choosing-pattern` | Choose the right pattern | `/plugin install pgdbm-choosing-pattern@juanre-ai-tools` |
| `pgdbm-shared-pool` | Production connection pooling | `/plugin install pgdbm-shared-pool@juanre-ai-tools` |
| `pgdbm-dual-mode` | Portable database libraries | `/plugin install pgdbm-dual-mode@juanre-ai-tools` |
| `pgdbm-standalone` | Standalone service pattern | `/plugin install pgdbm-standalone@juanre-ai-tools` |
| `pgdbm-testing` | Database testing patterns | `/plugin install pgdbm-testing@juanre-ai-tools` |
| `pgdbm-usage` | Basic operations | `/plugin install pgdbm-usage@juanre-ai-tools` |
| `pgdbm-core-api` | Complete API reference | `/plugin install pgdbm-core-api@juanre-ai-tools` |
| `pgdbm-migrations-api` | Migrations API reference | `/plugin install pgdbm-migrations-api@juanre-ai-tools` |
| `pgdbm-common-mistakes` | Common pitfalls to avoid | `/plugin install pgdbm-common-mistakes@juanre-ai-tools` |

### How It Works

**Example: Setting up a FastAPI app**

**You ask:**
> "Help me build a FastAPI app with PostgreSQL connection pooling"

**What happens:**
1. Claude sees "FastAPI", "PostgreSQL", "connection pooling"
2. Automatically loads `pgdbm-shared-pool` skill
3. Provides expert guidance with production patterns
4. Shows you exactly what you need

**Result:** Production-ready code following best practices, with proper pool management and schema isolation!

**Example: Testing database code**

**You ask:**
> "Show me how to test my database code with fixtures"

**What happens:**
1. Claude sees "test", "database", "fixtures"
2. Loads `pgdbm-testing` skill
3. Guides you through test setup and fixtures
4. Shows you how to use `test_db` and `test_db_with_schema`

**Result:** Complete test setup with automatic database cleanup and isolation!

## Quick Start

### Production-Ready Pattern (Recommended)

For production applications, use the **shared pool pattern** - it's the most efficient and scalable:

```python
# app.py - Complete production setup
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from pgdbm import AsyncDatabaseManager, DatabaseConfig
from pgdbm.migrations import AsyncMigrationManager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create ONE shared pool for entire application
    config = DatabaseConfig(
        connection_string="postgresql://localhost/myapp",
        # Pool sizing: start small, then tune using metrics and your DB's max_connections
        min_connections=5,
        max_connections=20,
    )
    shared_pool = await AsyncDatabaseManager.create_shared_pool(config)

    # Create schema-specific managers (share the pool)
    app.state.dbs = {
        'users': AsyncDatabaseManager(pool=shared_pool, schema="users"),
        'orders': AsyncDatabaseManager(pool=shared_pool, schema="orders"),
    }

    # Run migrations for each schema
    for name, db in app.state.dbs.items():
        migrations = AsyncMigrationManager(db, f"migrations/{name}", name)
        await migrations.apply_pending_migrations()

    yield
    await shared_pool.close()

app = FastAPI(lifespan=lifespan)

# Use with dependency injection
@app.post("/users")
async def create_user(email: str, request: Request):
    db = request.app.state.dbs['users']
    user_id = await db.fetch_value(
        "INSERT INTO {{tables.users}} (email) VALUES ($1) RETURNING id",
        email
    )
    return {"id": user_id}
```

### Simple Single-Service Setup

For simple applications with just one service:

```python
from pgdbm import AsyncDatabaseManager, DatabaseConfig, AsyncMigrationManager

# Configure and connect
config = DatabaseConfig(connection_string="postgresql://localhost/myapp")
db = AsyncDatabaseManager(config)
await db.connect()

# Apply migrations
migrations = AsyncMigrationManager(db, migrations_path="./migrations")
await migrations.apply_pending_migrations()

# Use your database
user_id = await db.fetch_value(
    "INSERT INTO {{tables.users}} (email) VALUES ($1) RETURNING id",
    "user@example.com"
)

# Clean up
await db.disconnect()
```

### Migration Files

```sql
-- migrations/001_initial.sql
CREATE TABLE IF NOT EXISTS {{tables.users}} (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

> **💡 Important:** Always use `{{tables.tablename}}` syntax - it automatically handles schema prefixes!

## Core Patterns

### 1. One Pool, Many Schemas

**This is the most important pattern in pgdbm:**

```python
# ✅ CORRECT: One shared pool for entire application
shared_pool = await AsyncDatabaseManager.create_shared_pool(config)
users_db = AsyncDatabaseManager(pool=shared_pool, schema="users")
orders_db = AsyncDatabaseManager(pool=shared_pool, schema="orders")
billing_db = AsyncDatabaseManager(pool=shared_pool, schema="billing")

# ❌ WRONG: Multiple pools (wastes connections, hits limits)
users_db = AsyncDatabaseManager(DatabaseConfig(...))   # Creates own pool
orders_db = AsyncDatabaseManager(DatabaseConfig(...))  # Another pool - BAD!
```

> **Why?** PostgreSQL has connection limits. Multiple pools waste connections and can exhaust your database. One shared pool is more efficient and prevents connection errors.

### 2. Module Isolation with Schemas

When multiple modules share a database, use schemas to prevent table conflicts:

```python
# Each module gets its own schema namespace
user_db = AsyncDatabaseManager(pool=shared_pool, schema="user_module")
blog_db = AsyncDatabaseManager(pool=shared_pool, schema="blog_module")

# Both can have a "users" table without conflict:
# - user_module.users
# - blog_module.users
```

The `{{tables.tablename}}` syntax in queries automatically expands to the correct schema-qualified name.

### 3. Migration Management

```python
# Migrations know their schema from the database manager
migrations = AsyncMigrationManager(
    db,                           # Schema is already set in db
    migrations_path="./migrations",
    module_name="myservice"       # Unique identifier for this service
)
result = await migrations.apply_pending_migrations()

# ⚠️ Common mistake: Don't pass schema to AsyncMigrationManager
# migrations = AsyncMigrationManager(db, path, schema="foo")  # WRONG - no schema param!
```

### 4. Transactions with Template Substitution

Transactions automatically handle `{{tables.}}` template substitution:

```python
async with db.transaction() as tx:
    # Create a user
    user_id = await tx.fetch_value(
        "INSERT INTO {{tables.users}} (email) VALUES ($1) RETURNING id",
        "alice@example.com"
    )

    # Create user profile in same transaction
    await tx.execute(
        "INSERT INTO {{tables.profiles}} (user_id, bio) VALUES ($1, $2)",
        user_id,
        "Software developer"
    )
    # Automatically committed on success, rolled back on exception
```

All transaction methods return dictionaries for consistency:
- `tx.execute()` - Execute without results
- `tx.fetch_one()` - Get single row as dict
- `tx.fetch_all()` - Get all rows as list of dicts
- `tx.fetch_value()` - Get single value

### 5. Testing Support

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

### 6. Monitoring

Track database performance:

```python
from pgdbm import MonitoredAsyncDatabaseManager

db = MonitoredAsyncDatabaseManager(
    config=config,
    slow_query_threshold_ms=100  # Log queries over 100ms
)

# Get metrics
metrics = await db.get_metrics()
slow_queries = await db.get_slow_queries(limit=10)
```

### 7. Production TLS and Timeouts

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

- **[Production Patterns Guide](docs/production-patterns.md)** - **START HERE!** Real-world patterns and best practices
- **📋 [Quick Reference](docs/quick-reference.md)** - Cheatsheet for common patterns and commands
- [Quickstart Guide](docs/quickstart.md) - Step-by-step getting started
- [CLI Reference](docs/cli.md) - Command-line interface documentation
- [Patterns Guide](docs/patterns.md) - Deployment patterns, dual-mode libraries, and framework integration
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
- New contributors should read the [Repository Guidelines](AGENTS.md) for a concise overview of project structure, tooling, and expectations.

### Testing & Modular Usage at a Glance

- Import `pgdbm.fixtures.conftest` in `tests/conftest.py` to unlock fixtures like `test_db`, `test_db_with_schema`, and `test_db_with_tables`; each test gets a fresh database, while `test_db_isolated` offers a faster transaction/savepoint path when you only need rollback semantics.
- Use markers (`slow`, `integration`, `unit`) and skip long runs locally with `pytest -m "not slow"`; monitor coverage via `pytest --cov src/pgdbm --cov-report=term-missing`.
- Libraries and services should accept either a connection string or an injected `AsyncDatabaseManager`, always run their own migrations (`module_name` scoped) and use `{{tables.*}}` templating so the same code works standalone or inside a shared pool; in pooled mode the schema prefix is inserted during query preparation, not via `search_path`, so every statement must use the template helpers.
- Parent apps create a single shared pool and hand schema-bound managers to each module (`AsyncDatabaseManager(pool=shared_pool, schema="module")`)—library composition is cooperative, meaning the host is responsible for wiring every participating module before they can reference each other.
- See `docs/testing.md` and `docs/production-patterns.md` for deeper walkthroughs and code samples.

## License

MIT License - see [LICENSE](LICENSE) for details.
