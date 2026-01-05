# pgdbm Quick Reference

## 🚀 Most Common Patterns (Copy & Paste)

### 1. FastAPI with Shared Pool (Recommended for 90% of cases)

```python
# app/database.py
from pgdbm import AsyncDatabaseManager, DatabaseConfig

async def create_database_infrastructure(connection_string: str):
    config = DatabaseConfig(
        connection_string=connection_string,
        # Pool sizing: start small, then tune using metrics and your DB's max_connections
        min_connections=5,
        max_connections=20,
    )

    # ONE shared pool for entire application
    shared_pool = await AsyncDatabaseManager.create_shared_pool(config)

    # Schema-specific managers
    return {
        'pool': shared_pool,
        'users': AsyncDatabaseManager(pool=shared_pool, schema="users"),
        'orders': AsyncDatabaseManager(pool=shared_pool, schema="orders"),
    }

# app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, Request
from typing import Annotated

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database
    db_infra = await create_database_infrastructure("postgresql://localhost/myapp")
    app.state.db_infra = db_infra

    # Run migrations for each schema
    for schema_name, db in db_infra.items():
        if schema_name != 'pool':
            migrations = AsyncMigrationManager(db, f"migrations/{schema_name}", schema_name)
            await migrations.apply_pending_migrations()

    yield

    # Cleanup
    await db_infra['pool'].close()

app = FastAPI(lifespan=lifespan)

# Dependency injection
async def get_users_db(request: Request) -> AsyncDatabaseManager:
    return request.app.state.db_infra['users']

UserDB = Annotated[AsyncDatabaseManager, Depends(get_users_db)]

# Routes
@app.post("/users")
async def create_user(email: str, db: UserDB):
    user_id = await db.fetch_value(
        "INSERT INTO {{tables.users}} (email) VALUES ($1) RETURNING id",
        email
    )
    return {"id": user_id}
```

### 2. Simple Single Service

```python
# For simple apps with one database
from pgdbm import AsyncDatabaseManager, DatabaseConfig

async def main():
    config = DatabaseConfig(connection_string="postgresql://localhost/myapp")
    db = AsyncDatabaseManager(config)
    await db.connect()

    # Use the database
    users = await db.fetch_all("SELECT * FROM {{tables.users}}")

    await db.disconnect()
```

### 3. Multi-Tenant SaaS

```python
# Tenant manager for SaaS applications
class TenantManager:
    def __init__(self, shared_pool):
        self.pool = shared_pool
        self.tenants = {}

    async def get_db(self, tenant_id: str) -> AsyncDatabaseManager:
        if tenant_id not in self.tenants:
            schema = f"tenant_{tenant_id}"
            self.tenants[tenant_id] = AsyncDatabaseManager(
                pool=self.pool,
                schema=schema
            )
        return self.tenants[tenant_id]

# Usage in FastAPI
@app.get("/api/{tenant_id}/users")
async def get_tenant_users(
    tenant_id: str,
    tenant_manager: Annotated[TenantManager, Depends(get_tenant_manager)]
):
    db = await tenant_manager.get_db(tenant_id)
    return await db.fetch_all("SELECT * FROM {{tables.users}}")
```

## 📋 Decision Flowchart

```
Start → How many services?
         ├─ One → Single Database Manager
         └─ Multiple → Shared Pool Pattern
                       ├─ Same tables? → Schema Isolation
                       └─ Different tables? → Service Schemas
                                            └─ Need library mode? → Dual-Mode Pattern
```

## ⚡ Command Cheatsheet

### Database Operations

```python
# Fetch operations
value = await db.fetch_value("SELECT COUNT(*) FROM {{tables.users}}")
row = await db.fetch_one("SELECT * FROM {{tables.users}} WHERE id = $1", 1)
rows = await db.fetch_all("SELECT * FROM {{tables.users}}")

# Write operations
await db.execute("INSERT INTO {{tables.users}} (email) VALUES ($1)", email)
emails = [("alice@example.com",), ("bob@example.com",)]
await db.executemany("INSERT INTO {{tables.users}} (email) VALUES ($1)", emails)

# Transactions
async with db.transaction():
    await db.execute("INSERT INTO {{tables.users}} ...")
    await db.execute("UPDATE {{tables.orders}} ...")
    # Automatically commits or rolls back

# Prepared statements
stmt = await db.prepare("SELECT * FROM {{tables.users}} WHERE email = $1")
user = await stmt.fetch_one(email)
```

### Migration Commands

```python
# Apply migrations
migrations = AsyncMigrationManager(db, "migrations", "myapp")
await migrations.apply_pending_migrations()

# Check status
pending = await migrations.get_pending_migrations()
applied = await migrations.get_applied_migrations()

# SQL migration file format
# migrations/001_initial.sql
CREATE TABLE IF NOT EXISTS {{tables.users}} (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL
);
```

### Testing

```python
# Test fixture
@pytest.fixture
async def db():
    async with AsyncTestDatabase.create(schema="test") as test_db:
        yield test_db

# Test function
async def test_user_creation(db):
    user_id = await db.fetch_value(
        "INSERT INTO {{tables.users}} (email) VALUES ($1) RETURNING id",
        "test@example.com"
    )
    assert user_id == 1
```

## 🚫 Anti-Patterns to Avoid

| ❌ Don't Do This | ✅ Do This Instead |
|-----------------|-------------------|
| Multiple `AsyncDatabaseManager(config)` | One `create_shared_pool()` + multiple managers |
| `db.schema = "new_schema"` | Create separate manager for each schema |
| `INSERT INTO users` | `INSERT INTO {{tables.users}}` |
| `request.app.state.db` everywhere | Use FastAPI dependency injection |
| Schema in `AsyncMigrationManager` | Schema in `AsyncDatabaseManager` |

## 🔧 Configuration Quick Reference

```python
config = DatabaseConfig(
    # Connection
    connection_string="postgresql://user:pass@host:5432/dbname",

    # Pool settings
    min_connections=5,         # Minimum pool size (connections opened eagerly)
    max_connections=20,        # Maximum pool size (cap)

    # Timeouts (in seconds)
    connect_timeout=5.0,       # Connection timeout
    command_timeout=30.0,      # Query timeout

    # Performance
    statement_cache_size=1000, # Prepared statement cache

    # SSL (for production)
    ssl_mode="require",        # require, verify-full, etc.
    ssl_cert="/path/to/cert",
    ssl_key="/path/to/key",
    ssl_ca="/path/to/ca",
)
```

## 🎯 Pattern Selection Matrix

| Scenario | Pattern | Key Code |
|----------|---------|----------|
| Simple CRUD API | Single Service | `db = AsyncDatabaseManager(config); await db.connect()` |
| Microservices | Shared Pool | `pool = await create_shared_pool(config)` |
| Multi-tenant SaaS | Schema Isolation | `AsyncDatabaseManager(pool=pool, schema=f"tenant_{id}")` |
| Reusable library | Dual-Mode | `create_app(db_manager=external_db, standalone=False)` |
| High-performance | Monitored + Prepared | `MonitoredAsyncDatabaseManager` + `db.prepare()` |

## 📊 Pool Size Guidelines

| Application Type | Min Connections | Max Connections |
|-----------------|-----------------|-----------------|
| Development | 2 | 10 |
| Small API (<100 req/s) | 5 | 20 |
| Medium API (100-1000 req/s) | 10 | 50 |
| Large API (>1000 req/s) | 20 | 100 |
| Background workers | 2 | 10 per worker |

Notes:
- For shared-pool deployments, these numbers apply to the ONE shared pool (total across all schemas/services).
- Keep `min_connections` low unless you have steady traffic; it is the pool floor.

## 🔍 Common Errors & Solutions

| Error | Cause | Solution |
|-------|-------|----------|
| `TimeoutError: failed to acquire connection` | Pool exhausted | Increase `max_connections` or use shared pool |
| `relation "users" does not exist` | Missing schema prefix | Use `{{tables.users}}` syntax |
| `schema "x" does not exist` | Schema not created | Run migrations or `CREATE SCHEMA` |
| `Migration already applied` | Duplicate module name | Use unique `module_name` per schema |
| `TypeError: 'schema' is not a parameter` | Wrong API usage | Schema goes in `AsyncDatabaseManager`, not `AsyncMigrationManager` |

## 🛠️ Debugging Commands

```python
# Check pool statistics
stats = await db.get_pool_stats()
print(f"Used: {stats['used_size']}, Free: {stats['free_size']}, Max: {stats['max_size']}")

# Check schema configuration
# Note: in shared-pool mode, pgdbm does NOT change search_path; it qualifies tables via templates.
print(f"Configured schema: {db.schema}")
print(db.prepare_query("SELECT * FROM {{tables.users}} LIMIT 1"))

# List all tables in schema
tables = await db.fetch_all("""
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = $1
""", db.schema)

# Check migration status
migrations = AsyncMigrationManager(db, "migrations", "myapp")
applied = await migrations.get_applied_migrations()
pending = await migrations.get_pending_migrations()
```

## 📚 Import Reference

```python
# Core functionality
from pgdbm import (
    AsyncDatabaseManager,    # Main database manager
    DatabaseConfig,          # Configuration class
)

# Migrations
from pgdbm.migrations import (
    AsyncMigrationManager,   # Migration runner
)

# Monitoring
from pgdbm.monitoring import (
    MonitoredAsyncDatabaseManager,  # With performance tracking
)

# Testing
from pgdbm.testing import (
    AsyncTestDatabase,       # Test database fixture
    DatabaseTestCase,        # Test case base class
)

# Errors
from pgdbm.errors import (
    DatabaseError,           # Base exception
    ConnectionError,         # Connection issues
    MigrationError,         # Migration problems
)
```

## 🔗 Quick Links

- [Production Patterns Guide](./production-patterns.md) - Detailed patterns
- [API Reference](./api-reference.md) - Complete API docs
- [Migration Guide](./migrations.md) - Migration details
- [Testing Guide](./testing.md) - Testing strategies
- [Examples](../examples/) - Working examples
