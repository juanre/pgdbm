# Production Patterns Guide

> **The complete guide to building production systems with pgdbm**

This guide contains battle-tested patterns for using pgdbm in production, based on real-world experience building and scaling applications. If you're building anything beyond a simple prototype, **start here**.

## 🎯 Quick Decision Guide

Not sure which pattern to use? Answer these questions:

1. **Are you building a single service?** → [Single Service Pattern](#single-service-pattern)
2. **Are you building multiple services?** → [Shared Pool Pattern](#shared-pool-pattern)
3. **Need multi-tenancy?** → [Schema Isolation Pattern](#schema-isolation-pattern)
4. **Building a reusable library?** → [Dual-Mode Library Pattern](#dual-mode-library-pattern)
5. **Using FastAPI?** → [FastAPI Integration Pattern](#fastapi-integration-pattern)

## 📋 Essential Rules

Before diving into patterns, understand these critical rules:

### Rule 1: One Pool to Rule Them All
```python
# ✅ CORRECT: One shared pool
shared_pool = await AsyncDatabaseManager.create_shared_pool(config)
server_db = AsyncDatabaseManager(pool=shared_pool, schema="server")
api_db = AsyncDatabaseManager(pool=shared_pool, schema="api")

# ❌ WRONG: Multiple pools (wastes connections, hits limits)
server_db = AsyncDatabaseManager(DatabaseConfig(...))  # Creates own pool
api_db = AsyncDatabaseManager(DatabaseConfig(...))     # Creates another pool
```

### Rule 2: Schemas are Permanent
```python
# ✅ CORRECT: Create a manager for each schema
db_server = AsyncDatabaseManager(pool=shared_pool, schema="server")
db_api = AsyncDatabaseManager(pool=shared_pool, schema="api")

# ❌ WRONG: Never switch schemas on a manager
db.schema = "different_schema"  # DON'T DO THIS!
```

### Rule 3: Use Template Syntax
```python
# ✅ CORRECT: Use templates for schema-aware queries
await db.execute("INSERT INTO {{tables.users}} (email) VALUES ($1)", email)

# ❌ WRONG: Hardcoding table names
await db.execute("INSERT INTO users (email) VALUES ($1)", email)
```

> **How schema isolation is enforced:** When you pass `schema="module"` to a manager that shares a pool, pgdbm qualifies tables at query preparation time (the `{{tables.*}}` placeholders expand to `"module".table`). No `search_path` change occurs for those pooled connections. When a manager owns its own pool, the schema is also added to the server settings and `search_path`, but the template expansion still runs so migrations and queries behave identically in both modes.

## 🏗️ Architecture Patterns

### Single Service Pattern

For simple applications with one service and one database.

```python
# main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pgdbm import AsyncDatabaseManager, DatabaseConfig
from pgdbm.migrations import AsyncMigrationManager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Single database manager
    config = DatabaseConfig(
        connection_string="postgresql://localhost/myapp",
        min_connections=5,
        max_connections=20,
    )

    db = AsyncDatabaseManager(config)
    await db.connect()
    app.state.db = db

    # Run migrations
    migrations = AsyncMigrationManager(
        db,
        migrations_path="migrations",
        module_name="myapp"
    )
    await migrations.apply_pending_migrations()

    yield

    await db.disconnect()

app = FastAPI(lifespan=lifespan)
```

### Shared Pool Pattern

For multiple services sharing a database. **This is the recommended pattern for most production systems.**

```python
# shared/database.py
from typing import Dict
from pgdbm import AsyncDatabaseManager, DatabaseConfig

class DatabaseInfrastructure:
    """Singleton managing shared database resources."""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self, config: DatabaseConfig) -> None:
        """Initialize shared pool and service managers."""
        if self._initialized:
            return

        # Create ONE shared pool for all services
        self.shared_pool = await AsyncDatabaseManager.create_shared_pool(config)

        # Create schema-specific managers
        self.managers = {
            'users': AsyncDatabaseManager(pool=self.shared_pool, schema="users"),
            'orders': AsyncDatabaseManager(pool=self.shared_pool, schema="orders"),
            'inventory': AsyncDatabaseManager(pool=self.shared_pool, schema="inventory"),
        }

        self._initialized = True

    async def close(self) -> None:
        """Clean shutdown."""
        if self.shared_pool:
            await self.shared_pool.close()

# Usage in services
db_infra = DatabaseInfrastructure()
await db_infra.initialize(config)
users_db = db_infra.managers['users']
```

### Schema Isolation Pattern

For multi-tenant applications or service isolation.

```python
# Multi-tenant architecture
class TenantManager:
    def __init__(self, shared_pool):
        self.shared_pool = shared_pool
        self.tenant_dbs = {}

    async def get_tenant_db(self, tenant_id: str) -> AsyncDatabaseManager:
        """Get or create a database manager for a tenant."""
        if tenant_id not in self.tenant_dbs:
            schema = f"tenant_{tenant_id}"

            # Create schema if it doesn't exist
            admin_db = AsyncDatabaseManager(pool=self.shared_pool, schema="public")
            await admin_db.execute(f"CREATE SCHEMA IF NOT EXISTS {schema}")

            # Create tenant-specific manager
            self.tenant_dbs[tenant_id] = AsyncDatabaseManager(
                pool=self.shared_pool,
                schema=schema
            )

            # Run tenant migrations
            migrations = AsyncMigrationManager(
                self.tenant_dbs[tenant_id],
                migrations_path="tenant_migrations",
                module_name=f"tenant_{tenant_id}"
            )
            await migrations.apply_pending_migrations()

        return self.tenant_dbs[tenant_id]
```

### Dual-Mode Library Pattern

For libraries that can run standalone or embedded.

```python
# mylib/app.py
def create_app(
    db_manager: Optional[AsyncDatabaseManager] = None,
    schema: str = "mylib",
    standalone: bool = True,
) -> FastAPI:
    """
    Create app supporting both standalone and library modes.

    Args:
        db_manager: External database manager (library mode)
        schema: Schema name for this library's tables
        standalone: If True, manage own database lifecycle
    """

    if standalone:
        app = FastAPI(lifespan=lifespan)
    else:
        app = FastAPI()  # No lifespan - parent manages database

    if not standalone:
        if not db_manager:
            raise ValueError("db_manager required when standalone=False")
        app.state.db = db_manager
        app.state.external_db = True

    return app

# Parent app usage
from mylib import create_app as create_mylib_app

# In library mode
mylib_db = AsyncDatabaseManager(pool=shared_pool, schema="mylib")
mylib_app = create_mylib_app(
    db_manager=mylib_db,
    standalone=False
)
app.mount("/mylib", mylib_app)
```

### FastAPI Integration Pattern

Clean dependency injection with FastAPI.

```python
# dependencies.py
from fastapi import Request, Depends, HTTPException
from typing import Annotated

async def get_db(request: Request) -> AsyncDatabaseManager:
    """Database dependency."""
    if not hasattr(request.app.state, 'db'):
        raise HTTPException(500, "Database not initialized")
    return request.app.state.db

# Type alias for cleaner signatures
DatabaseDep = Annotated[AsyncDatabaseManager, Depends(get_db)]

# routes.py
from fastapi import APIRouter
from dependencies import DatabaseDep

router = APIRouter()

@router.post("/users")
async def create_user(
    email: str,
    db: DatabaseDep,  # Clean dependency injection
):
    user_id = await db.fetch_value(
        "INSERT INTO {{tables.users}} (email) VALUES ($1) RETURNING id",
        email
    )
    return {"id": user_id}
```

## 🚀 Migration Patterns

### Basic Migrations

```sql
-- migrations/001_initial.sql
CREATE TABLE IF NOT EXISTS {{tables.users}} (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS users_email
ON {{tables.users}} (email);
```

### Cross-Schema References

```sql
-- When you need to reference another schema
CREATE TABLE IF NOT EXISTS {{tables.orders}} (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users_schema.users(id),
    total DECIMAL(10,2)
);
```

### Safe Migrations

```python
# Always run migrations in a transaction
async def apply_migrations_safely(db: AsyncDatabaseManager):
    async with db.transaction():
        migrations = AsyncMigrationManager(
            db,
            migrations_path="migrations",
            module_name="myapp"
        )
        await migrations.apply_pending_migrations()
```

## 🧪 Testing Patterns

### Test Database Setup

```python
# tests/conftest.py
import pytest
from pgdbm.testing import AsyncTestDatabase

@pytest.fixture
async def test_db():
    """Create isolated test database."""
    async with AsyncTestDatabase.create(
        schema="test_schema",
        cleanup=True
    ) as db:
        # Run migrations
        migrations = AsyncMigrationManager(
            db,
            migrations_path="migrations",
            module_name="test"
        )
        await migrations.apply_pending_migrations()

        yield db

# tests/test_users.py
async def test_create_user(test_db):
    user_id = await test_db.fetch_value(
        "INSERT INTO {{tables.users}} (email) VALUES ($1) RETURNING id",
        "test@example.com"
    )
    assert user_id == 1
```

### Testing with Shared Pools

```python
@pytest.fixture
async def test_infrastructure():
    """Test infrastructure with shared pool."""
    config = DatabaseConfig(
        connection_string="postgresql://localhost/test_db",
        min_connections=2,
        max_connections=5,
    )

    shared_pool = await AsyncDatabaseManager.create_shared_pool(config)

    # Create test managers
    managers = {
        'service1': AsyncDatabaseManager(pool=shared_pool, schema="test_service1"),
        'service2': AsyncDatabaseManager(pool=shared_pool, schema="test_service2"),
    }

    yield managers

    await shared_pool.close()
```

## ⚠️ Common Mistakes and Solutions

### Mistake 1: Creating Multiple Pools

```python
# ❌ WRONG: Each service creates its own pool
class UserService:
    def __init__(self):
        self.db = AsyncDatabaseManager(DatabaseConfig(...))  # New pool!

class OrderService:
    def __init__(self):
        self.db = AsyncDatabaseManager(DatabaseConfig(...))  # Another pool!

# ✅ CORRECT: Services share a pool
shared_pool = await AsyncDatabaseManager.create_shared_pool(config)
user_service = UserService(AsyncDatabaseManager(pool=shared_pool, schema="users"))
order_service = OrderService(AsyncDatabaseManager(pool=shared_pool, schema="orders"))
```

### Mistake 2: Dynamic Schema Switching

```python
# ❌ WRONG: Switching schemas at runtime
async def get_tenant_data(db, tenant_id):
    db.schema = f"tenant_{tenant_id}"  # Race condition!
    return await db.fetch_all("SELECT * FROM {{tables.data}}")

# ✅ CORRECT: Pre-create managers for each schema
tenant_dbs = {
    tenant_id: AsyncDatabaseManager(pool=shared_pool, schema=f"tenant_{tenant_id}")
    for tenant_id in tenant_ids
}

async def get_tenant_data(tenant_id):
    db = tenant_dbs[tenant_id]
    return await db.fetch_all("SELECT * FROM {{tables.data}}")
```

### Mistake 3: Forgetting Migration Schema

```python
# ❌ WRONG: Trying to pass schema to AsyncMigrationManager
migrations = AsyncMigrationManager(
    db,
    migrations_path="migrations",
    schema="myschema"  # This parameter doesn't exist!
)

# ✅ CORRECT: Schema comes from the database manager
db = AsyncDatabaseManager(pool=shared_pool, schema="myschema")
migrations = AsyncMigrationManager(
    db,  # Schema is already in the db manager
    migrations_path="migrations",
    module_name="myapp"
)
```

### Mistake 4: Not Using Dependency Injection

```python
# ❌ WRONG: Accessing database through request.app.state
@router.post("/users")
async def create_user(request: Request, email: str):
    db = request.app.state.db  # Hard to test, tightly coupled
    # ...

# ✅ CORRECT: Use dependency injection
@router.post("/users")
async def create_user(email: str, db: DatabaseDep):
    # Clean, testable, loosely coupled
    # ...
```

## 📊 Performance Optimization

### Connection Pool Tuning

```python
# Production configuration
config = DatabaseConfig(
    connection_string="postgresql://localhost/myapp",

    # Pool settings
    min_connections=20,      # Minimum pool size (connections opened eagerly)
    max_connections=100,     # Maximum pool size (cap)

    # Timeouts
    connect_timeout=5.0,     # Connection timeout
    command_timeout=30.0,    # Query timeout

    # Performance
    statement_cache_size=1000,  # Prepared statement cache

    # SSL for production
    ssl_mode="require",
)
```

### Query Optimization

```python
# Use prepared statements for repeated queries
user_query = await db.prepare(
    "SELECT * FROM {{tables.users}} WHERE email = $1"
)

# Execute many times efficiently
for email in emails:
    user = await user_query.fetch_one(email)
```

### Monitoring Slow Queries

```python
from pgdbm import MonitoredAsyncDatabaseManager

# Use monitored manager in production
db = MonitoredAsyncDatabaseManager(
    pool=shared_pool,
    schema="myapp",
    slow_query_threshold_ms=1000,  # Track queries slower than 1 second
)

# Check for slow queries periodically
slow_queries = db.get_slow_queries()
for query in slow_queries:
    logger.warning(f"Slow query ({query.duration_ms}ms): {query.query}")
```

## 🔧 Troubleshooting

### Connection Pool Exhaustion

**Symptoms**: `TimeoutError: failed to acquire connection`

**Solutions**:
1. Increase `max_connections` in config
2. Ensure you're using ONE shared pool
3. Check for connection leaks (transactions not closed)
4. Monitor with `await db.get_pool_stats()`

### Schema Not Found

**Symptoms**: `relation "users" does not exist`

**Solutions**:
1. Ensure migrations have run for the schema
2. Check you're using `{{tables.tablename}}` syntax
3. Verify the database manager has the correct schema set
4. Debug by printing `db.schema` and inspecting `db.prepare_query(...)` output (shared-pool mode does not use `search_path`)

### Migration Conflicts

**Symptoms**: `Migration already applied` or `Migration order conflict`

**Solutions**:
1. Use unique module names for each schema's migrations
2. Check migration naming (must be `NNN_description.sql`)
3. Clear migration history if needed: `DELETE FROM schema_migrations WHERE module = 'mymodule'`

## 📚 Quick Reference

### Essential Imports
```python
from pgdbm import (
    AsyncDatabaseManager,
    DatabaseConfig,
    AsyncMigrationManager,
    MonitoredAsyncDatabaseManager,
)
from pgdbm.testing import AsyncTestDatabase
```

### Connection Lifecycle
```python
# Create
config = DatabaseConfig(connection_string="postgresql://...")
pool = await AsyncDatabaseManager.create_shared_pool(config)
db = AsyncDatabaseManager(pool=pool, schema="myschema")

# Use
async with db.transaction():
    await db.execute("INSERT INTO {{tables.users}} ...")

# Cleanup
await pool.close()
```

### Query Patterns
```python
# Single value
count = await db.fetch_value("SELECT COUNT(*) FROM {{tables.users}}")

# Single row
user = await db.fetch_one("SELECT * FROM {{tables.users}} WHERE id = $1", user_id)

# Multiple rows
users = await db.fetch_all("SELECT * FROM {{tables.users}}")

# No return value
await db.execute("DELETE FROM {{tables.users}} WHERE id = $1", user_id)
```

## 🎓 Learning Path

1. **Start Simple**: Begin with the [Single Service Pattern](#single-service-pattern)
2. **Add Services**: Move to [Shared Pool Pattern](#shared-pool-pattern) when you have multiple services
3. **Add Tenancy**: Implement [Schema Isolation](#schema-isolation-pattern) for multi-tenancy
4. **Build Libraries**: Use [Dual-Mode Pattern](#dual-mode-library-pattern) for reusable components
5. **Optimize**: Apply [Performance Optimization](#performance-optimization) patterns

## 📖 Further Reading

- [API Reference](./api-reference.md) - Complete API documentation
- [CLI Guide](./cli.md) - Command-line tools
- [Migration Guide](./migrations.md) - Advanced migration patterns
- [Testing Guide](./testing.md) - Comprehensive testing strategies

---

*Based on real-world production experience. Last updated: 2026*
