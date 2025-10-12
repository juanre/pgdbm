# PGDBM Patterns Guide: Lessons from LLMRing Architecture

This document captures the hard-won lessons and correct patterns for using pgdbm in production applications, based on our experience refactoring llmring-server and llmring-api to use clean, maintainable patterns.

## Table of Contents
1. [Core Principles](#core-principles)
2. [The Shared Pool Pattern](#the-shared-pool-pattern)
3. [Schema Isolation Pattern](#schema-isolation-pattern)
4. [Dependency Injection Pattern](#dependency-injection-pattern)
5. [Dual-Mode Library Pattern](#dual-mode-library-pattern)
6. [Migration Management](#migration-management)
7. [Testing Patterns](#testing-patterns)
8. [Common Pitfalls and How to Avoid Them](#common-pitfalls-and-how-to-avoid-them)
9. [Complete Example Implementation](#complete-example-implementation)

---

## Core Principles

### 1. One Pool to Rule Them All
**Principle**: Use ONE shared connection pool across your entire application, not multiple pools.

**Motivation**:
- Database connections are expensive resources
- PostgreSQL has connection limits
- Multiple pools can lead to connection exhaustion
- Shared pool ensures efficient resource utilization

**Implementation**:
```python
# ✅ CORRECT: One shared pool
shared_pool = await AsyncDatabaseManager.create_shared_pool(db_config)
server_db = AsyncDatabaseManager(pool=shared_pool, schema="server_schema")
api_db = AsyncDatabaseManager(pool=shared_pool, schema="api_schema")

# ❌ WRONG: Multiple pools
server_db = AsyncDatabaseManager(DatabaseConfig(...))  # Creates its own pool
api_db = AsyncDatabaseManager(DatabaseConfig(...))     # Creates another pool
```

### 2. Schema Isolation, Not Database Isolation
**Principle**: Use PostgreSQL schemas within a single database for service separation.

**Motivation**:
- Schemas provide logical separation without resource overhead
- Enables atomic cross-schema transactions when needed
- Simplifies connection management
- Reduces operational complexity

**Implementation**:
```python
# Each service gets its own schema but shares the pool
server_db = AsyncDatabaseManager(pool=shared_pool, schema="llmring")
api_db = AsyncDatabaseManager(pool=shared_pool, schema="llmring_api")
```

### 3. Managers are Permanently Bound to Schemas
**Principle**: Once a database manager is created with a schema, it should never switch schemas.

**Motivation**:
- Prevents accidental cross-schema operations
- Makes code easier to reason about
- Eliminates race conditions from schema switching
- Each manager has a clear, single responsibility

**Anti-pattern we initially tried**:
```python
# ❌ WRONG: Switching schemas
async def bad_pattern(db, schema):
    db.schema = schema  # Don't do this!
    await db.execute(...)
```

---

## The Shared Pool Pattern

### Creating the Shared Pool

```python
from pgdbm import AsyncDatabaseManager, DatabaseConfig

async def create_database_infrastructure():
    # Create configuration for the shared pool
    db_config = DatabaseConfig(
        connection_string="postgresql://localhost/myapp",
        min_connections=20,
        max_connections=50,
    )

    # Create the shared pool
    shared_pool = await AsyncDatabaseManager.create_shared_pool(db_config)

    # Create schema-specific managers from the pool
    server_db = AsyncDatabaseManager(pool=shared_pool, schema="server")
    api_db = AsyncDatabaseManager(pool=shared_pool, schema="api")
    analytics_db = AsyncDatabaseManager(pool=shared_pool, schema="analytics")

    return {
        'pool': shared_pool,
        'server': server_db,
        'api': api_db,
        'analytics': analytics_db,
    }
```

### Why This Pattern?

1. **Resource Efficiency**: 50 connections shared is better than 3×20 connections
2. **Connection Limits**: Production databases have connection limits
3. **Performance**: Connection pooling overhead happens once
4. **Monitoring**: Single pool to monitor and tune

---

## Schema Isolation Pattern

### Design Philosophy

Each logical service component gets its own PostgreSQL schema:

```
myapp_database/
├── server/          # Core server tables (aliases, usage, receipts)
│   ├── aliases
│   ├── usage_logs
│   └── receipts
├── api/             # API-specific tables (users, auth, projects)
│   ├── users
│   ├── api_keys
│   └── projects
└── analytics/       # Analytics tables
    ├── aggregates
    └── reports
```

### Implementation

```python
# Each service uses its schema-bound manager
class ServerService:
    def __init__(self, db: AsyncDatabaseManager):
        self.db = db  # Already bound to 'server' schema

    async def create_alias(self, name: str, target: str):
        # The {{tables.aliases}} template automatically uses the schema
        await self.db.execute(
            "INSERT INTO {{tables.aliases}} (name, target) VALUES ($1, $2)",
            name, target
        )

class APIService:
    def __init__(self, db: AsyncDatabaseManager):
        self.db = db  # Already bound to 'api' schema

    async def create_user(self, email: str):
        # This will use api.users, not server.users
        await self.db.execute(
            "INSERT INTO {{tables.users}} (email) VALUES ($1)",
            email
        )
```

### Benefits

1. **Clear Boundaries**: Each service owns its schema
2. **No Conflicts**: Table names can be reused across schemas
3. **Security**: Can apply schema-level permissions
4. **Migration Isolation**: Each schema has independent migrations

---

## Dependency Injection Pattern

### The Problem

Initial approach using `request.app.state.db` everywhere:
```python
# ❌ WRONG: Tightly coupled to request object
@router.post("/endpoint")
async def endpoint(request: Request):
    db = request.app.state.db  # Hard to test, tightly coupled
    result = await db.fetch_one(...)
```

### The Solution

Use FastAPI's dependency injection system:

```python
# dependencies.py
from fastapi import Request, HTTPException
from pgdbm import AsyncDatabaseManager

async def get_api_db(request: Request) -> AsyncDatabaseManager:
    """Get API database manager from app state."""
    if hasattr(request.app.state, 'databases'):
        return request.app.state.databases['api']
    raise HTTPException(status_code=500, detail="Database not initialized")

async def get_server_db(request: Request) -> AsyncDatabaseManager:
    """Get server database manager from app state."""
    if hasattr(request.app.state, 'databases'):
        return request.app.state.databases['server']
    raise HTTPException(status_code=500, detail="Database not initialized")
```

```python
# routers.py
from fastapi import Depends
from dependencies import get_api_db

@router.post("/endpoint")
async def endpoint(
    data: RequestModel,
    db: AsyncDatabaseManager = Depends(get_api_db),
):
    # Clean, testable, explicit dependencies
    result = await db.fetch_one(...)
```

### Testing with Dependency Injection

```python
# In tests, you can override dependencies
app.dependency_overrides[get_api_db] = lambda: test_db

# This makes testing much cleaner than trying to mock request.app.state
```

---

## Dual-Mode Library Pattern

### The Challenge

We needed llmring-server to work both:
1. **Standalone**: As an independent service with its own database
2. **Library**: Embedded in llmring-api using a shared database

### The Solution

```python
def create_app(
    db_manager: Optional[AsyncDatabaseManager] = None,
    run_migrations: bool = True,
    schema: Optional[str] = None,
    settings: Optional[Settings] = None,
    standalone: bool = True,
    include_meta_routes: bool = True,
) -> FastAPI:
    """Create app supporting both standalone and library modes."""

    if standalone:
        # Include lifespan for database management
        app = FastAPI(lifespan=lifespan)
    else:
        # No lifespan - parent app manages database
        app = FastAPI()

    # In library mode, set database immediately
    if not standalone:
        if not db_manager:
            raise ValueError("db_manager required when standalone=False")
        app.state.db = db_manager
        app.state.external_db = True
```

### Key Decisions

1. **`standalone` parameter**: Controls whether app manages its own database lifecycle
2. **`include_meta_routes` parameter**: Prevents route conflicts when mounting
3. **Lifespan management**: Only in standalone mode
4. **Database lifecycle**: Parent app responsible in library mode

### Usage in Parent App (llmring-api)

```python
# Create server app in library mode
server_app = create_app(
    db_manager=server_db,
    schema="llmring",
    run_migrations=True,
    standalone=False,          # Library mode
    include_meta_routes=False,  # Avoid route conflicts
)

# Override dependencies
server_app.dependency_overrides[get_db] = lambda: server_db

# Mount the server app
app.mount("", server_app, name="llmring_server")
```

---

## Migration Management

### Correct Pattern

```python
from pgdbm.migrations import AsyncMigrationManager

# The database manager already knows its schema
migrations = AsyncMigrationManager(
    db,  # Schema is already configured in the db manager
    migrations_path=str(migrations_path),
    module_name="service_name"  # Just the service name, no schema
)
await migrations.apply_pending_migrations()
```

### Common Mistake

```python
# ❌ WRONG: AsyncMigrationManager doesn't take a schema parameter
migrations = AsyncMigrationManager(
    db,
    migrations_path=str(migrations_path),
    module_name="service_name",
    schema="my_schema"  # This parameter doesn't exist!
)
```

### Migration Files

Use pgdbm's template syntax in migrations:
```sql
-- migrations/001_initial.sql
CREATE TABLE IF NOT EXISTS {{tables.users}} (
    id SERIAL PRIMARY KEY,
    email TEXT UNIQUE NOT NULL
);

-- This becomes schema.users automatically based on the db manager's schema
```

---

## Testing Patterns

### Test Database Setup

```python
@pytest_asyncio.fixture
async def test_databases(test_db_factory):
    """Create test databases with isolated schemas."""
    # Create shared pool for tests
    test_db = await test_db_factory.create_db(
        suffix="test",
        schema="test_schema"
    )

    # Create test-specific managers
    server_db = AsyncDatabaseManager(pool=test_db.pool, schema="test_server")
    api_db = AsyncDatabaseManager(pool=test_db.pool, schema="test_api")

    # Apply migrations
    for db, schema, migration_path in [
        (server_db, "test_server", "src/server/migrations"),
        (api_db, "test_api", "src/api/migrations"),
    ]:
        migrations = AsyncMigrationManager(
            db,
            migrations_path=migration_path,
            module_name=f"test_{schema}"
        )
        await migrations.apply_pending_migrations()

    return {'server': server_db, 'api': api_db}
```

### Testing with Dependency Overrides

```python
@pytest_asyncio.fixture
async def test_app(test_databases):
    """Create test app with dependency overrides."""
    from main import create_app
    from dependencies import get_db

    app = create_app(
        db_manager=test_databases['server'],
        standalone=False,  # No lifespan in tests
    )

    # Override dependencies for testing
    app.dependency_overrides[get_db] = lambda: test_databases['server']

    # Create test client
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
```

---

## Common Pitfalls and How to Avoid Them

### Pitfall 1: Multiple Connection Pools

**Wrong**:
```python
# Each service creates its own pool
class ServerService:
    def __init__(self):
        self.db = AsyncDatabaseManager(DatabaseConfig(...))

class APIService:
    def __init__(self):
        self.db = AsyncDatabaseManager(DatabaseConfig(...))
```

**Right**:
```python
# Services share a pool but use different schemas
shared_pool = await AsyncDatabaseManager.create_shared_pool(config)
server_service = ServerService(AsyncDatabaseManager(pool=shared_pool, schema="server"))
api_service = APIService(AsyncDatabaseManager(pool=shared_pool, schema="api"))
```

### Pitfall 2: Schema Switching

**Wrong**:
```python
async def process_request(db, tenant_id):
    db.schema = f"tenant_{tenant_id}"  # Don't switch schemas!
    await db.execute(...)
```

**Right**:
```python
# Create a manager for each schema upfront
tenants = {}
for tenant_id in tenant_ids:
    tenants[tenant_id] = AsyncDatabaseManager(
        pool=shared_pool,
        schema=f"tenant_{tenant_id}"
    )

async def process_request(tenant_id):
    db = tenants[tenant_id]  # Use pre-created manager
    await db.execute(...)
```

### Pitfall 3: Route Conflicts When Mounting

**Wrong**:
```python
# Both apps define root endpoint
app.mount("", server_app)  # Server's "/" conflicts with app's "/"
```

**Right**:
```python
# Use include_meta_routes parameter
server_app = create_app(
    include_meta_routes=False,  # Don't include / and /health
    ...
)
app.mount("", server_app)  # No conflicts
```

### Pitfall 4: Forgetting Dependency Overrides

**Wrong**:
```python
# Mount app without overriding dependencies
app.mount("", server_app)
# Server app still uses its own database references
```

**Right**:
```python
# Override dependencies before mounting
from server.dependencies import get_db as server_get_db
server_app.dependency_overrides[server_get_db] = lambda: our_server_db
app.mount("", server_app)
```

---

## Complete Example Implementation

Here's a complete example showing all patterns together:

```python
# main.py
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI
from pgdbm import AsyncDatabaseManager, DatabaseConfig
from pgdbm.migrations import AsyncMigrationManager

from config import Settings
from dependencies import get_api_db, get_server_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle with proper database setup."""
    settings = Settings()

    # Create shared pool
    db_config = DatabaseConfig(
        connection_string=settings.database_url,
        min_connections=20,
        max_connections=50,
    )
    shared_pool = await AsyncDatabaseManager.create_shared_pool(db_config)

    # Create schema-specific managers
    server_db = AsyncDatabaseManager(pool=shared_pool, schema="server")
    api_db = AsyncDatabaseManager(pool=shared_pool, schema="api")

    # Store in app state with clear structure
    app.state.databases = {
        'server': server_db,
        'api': api_db,
        'pool': shared_pool,
    }

    # Run migrations for each schema
    for db, schema_name, migration_path in [
        (server_db, "server", "src/server/migrations"),
        (api_db, "api", "src/api/migrations"),
    ]:
        migrations = AsyncMigrationManager(
            db,
            migrations_path=migration_path,
            module_name=f"app_{schema_name}"
        )
        await migrations.apply_pending_migrations()

    try:
        yield
    finally:
        # Clean shutdown
        await shared_pool.close()

def create_app() -> FastAPI:
    """Create application with proper patterns."""
    app = FastAPI(lifespan=lifespan)

    # Include routers with dependency injection
    from routers import api_router, server_router
    app.include_router(api_router)
    app.include_router(server_router)

    return app

# dependencies.py
from fastapi import Request, HTTPException
from pgdbm import AsyncDatabaseManager

async def get_server_db(request: Request) -> AsyncDatabaseManager:
    """Get server database (dependency injection)."""
    if not hasattr(request.app.state, 'databases'):
        raise HTTPException(500, "Database not initialized")
    return request.app.state.databases['server']

async def get_api_db(request: Request) -> AsyncDatabaseManager:
    """Get API database (dependency injection)."""
    if not hasattr(request.app.state, 'databases'):
        raise HTTPException(500, "Database not initialized")
    return request.app.state.databases['api']

# routers.py
from fastapi import APIRouter, Depends
from pgdbm import AsyncDatabaseManager

from dependencies import get_server_db, get_api_db

server_router = APIRouter(prefix="/api/v1")

@server_router.post("/aliases")
async def create_alias(
    data: dict,
    db: AsyncDatabaseManager = Depends(get_server_db),
):
    """Clean endpoint with dependency injection."""
    await db.execute(
        "INSERT INTO {{tables.aliases}} (name, target) VALUES ($1, $2)",
        data['name'], data['target']
    )
    return {"status": "created"}
```

---

## Summary of Key Learnings

1. **Use one shared pool** - Resource efficiency and connection management
2. **Schema isolation** - Logical separation without resource overhead
3. **Permanent schema binding** - Managers never switch schemas
4. **Dependency injection** - Clean, testable code
5. **Dual-mode support** - Libraries can work standalone or embedded
6. **Template syntax** - Use `{{tables.tablename}}` for schema-aware queries
7. **Proper lifecycle management** - Clear ownership of resources
8. **Testing patterns** - Override dependencies, not monkey-patch state

These patterns emerged from real-world experience building a production system. Following them will lead to cleaner, more maintainable, and more testable code.

---

*Document version: 1.0*
*Based on: llmring-server and llmring-api refactoring (2024)*
*pgdbm version: 0.1.0+*
