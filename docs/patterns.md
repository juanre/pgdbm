# Deployment Patterns Guide

This guide helps you choose the right pattern for using pgdbm in your application or library.

## Overview: Three Main Patterns

1. **Standalone Service (Owner)** - Module owns and manages its database connection and migrations
2. **Reusable Library (Flexible)** - Module can own the DB or use one owned by another; always runs its migrations
3. **Shared Pool Application (Consumer)** - Multiple modules share one database/pool with schema isolation

## Pattern 1: Standalone Service (Owner)

Use this when your service runs independently and owns its database.

### When to Use

- Microservices that run separately
- Development and testing environments
- Simple applications with one database
- Services that can't share connections

### Implementation

```python
from pgdbm import AsyncDatabaseManager, DatabaseConfig, AsyncMigrationManager

class MyService:
    def __init__(self):
        self.db = None

    async def initialize(self):
        # Create own connection
        config = DatabaseConfig(
            connection_string="postgresql://localhost/myservice",
            min_connections=10,
            max_connections=20
        )
        self.db = AsyncDatabaseManager(config)
        await self.db.connect()

        # Run migrations
        migrations = AsyncMigrationManager(
            self.db,
            migrations_path="./migrations",
            module_name="myservice"
        )
        await migrations.apply_pending_migrations()

    async def shutdown(self):
        if self.db:
            await self.db.disconnect()
```

### Pros and Cons

✅ **Pros:**
- Simple to understand and implement
- Complete control over connection pool
- Easy to scale independently
- Clear ownership boundaries

❌ **Cons:**
- Uses more database connections
- Can't share resources with other services
- Each service needs its own configuration

## Pattern 2: Reusable Library (Flexible)

Use this when building a library that will be used by other applications (like memory-service).

### When to Use

- Building packages for PyPI
- Creating internal shared libraries
- Making pluggable components
- Writing framework extensions

### Implementation

```python
from typing import Optional
from pgdbm import AsyncDatabaseManager, AsyncMigrationManager

class MyLibrary:
    """A library that can work standalone or with shared pools."""

    def __init__(
        self,
        connection_string: Optional[str] = None,
        db_manager: Optional[AsyncDatabaseManager] = None,
        schema: Optional[str] = None
    ):
        if not connection_string and not db_manager:
            raise ValueError("Either connection_string or db_manager required")

        self._external_db = db_manager is not None
        self.db = db_manager
        self._connection_string = connection_string
        self._schema = schema

    async def initialize(self):
        # Create connection if not provided
        if not self._external_db:
            config = DatabaseConfig(
                connection_string=self._connection_string,
                schema=self._schema
            )
            self.db = AsyncDatabaseManager(config)
            await self.db.connect()

        # ALWAYS run your own migrations
        migrations = AsyncMigrationManager(
            self.db,
            migrations_path=Path(__file__).parent / "migrations",
            module_name="my_library"  # Unique name!
        )
        await migrations.apply_pending_migrations()

    async def close(self):
        # Only close if we created the connection
        if self.db and not self._external_db:
            await self.db.disconnect()

    # Library methods
    async def do_something(self):
        return await self.db.fetch_all(
            "SELECT * FROM {{tables.my_table}}"
        )
```

### Usage Examples

**Standalone mode:**
```python
library = MyLibrary(connection_string="postgresql://localhost/mydb")
await library.initialize()
```

**Shared pool mode:**
```python
# Parent application creates pool
shared_pool = await AsyncDatabaseManager.create_shared_pool(config)
db_manager = AsyncDatabaseManager(pool=shared_pool, schema="my_library")

# Pass to library
library = MyLibrary(db_manager=db_manager)
await library.initialize()
```

### Key Principles

1. **Support both modes** - Accept optional `db_manager` and `schema`
2. **Always run your own migrations** - Your module owns its schema, even on a shared DB
3. **Use `{{tables.}}` syntax** - Makes migrations/queries portable across schemas
4. **Use a unique `module_name`** - Isolates migration history
5. **Clean up conditionally** - Only if you created the connection
6. **Composition is explicit** - Parent apps (or higher-level libraries) must construct database managers for every participating module and pass them in; pgdbm does not auto-wire nested libraries.

### Pros and Cons

✅ **Pros:**
- Flexible deployment options
- Works standalone or integrated
- Encapsulates schema management
- Reusable across projects

❌ **Cons:**
- More complex initialization
- Must handle both patterns
- Requires careful cleanup logic

## Pattern 2B: Dual-Mode Library (Extended)

This pattern extends Pattern 2 to show how to build libraries that can work both standalone and as part of a larger application, with special focus on FastAPI services and the pgdbm CLI.

### When to Use

- Building services that need both standalone and integrated deployment
- Creating pluggable FastAPI applications
- Developing services that will be extended by other services
- Supporting both CLI and library usage

### Implementation with pgdbm CLI

The pgdbm CLI can generate a complete dual-mode library scaffold:

```bash
# Generate dual-mode library with FastAPI
pgdbm generate library my_service --dual-mode --with-api

# This creates:
# my_service/
# ├── src/my_service/
# │   ├── __init__.py
# │   ├── main.py        # Dual-mode FastAPI app
# │   ├── cli.py         # Standalone CLI
# │   ├── core.py        # Service logic
# │   └── database.py    # Dual-mode database
# ├── migrations/
# │   └── 001_initial.sql
# ├── tests/
# │   └── test_my_service.py
# ├── pyproject.toml
# └── README.md
```

### Dual-Mode FastAPI Service

```python
# my_service/main.py
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pgdbm import AsyncDatabaseManager, AsyncMigrationManager
from pathlib import Path

def create_app(
    db_manager: Optional[AsyncDatabaseManager] = None,
    run_migrations: bool = True,
    schema: Optional[str] = None,
    config: Optional[dict] = None
) -> FastAPI:
    """Create service app supporting both standalone and library modes.

    Args:
        db_manager: External database (library mode) or None (standalone)
        run_migrations: Whether to apply migrations on startup
        schema: Override schema name
        config: Override configuration

    Returns:
        Configured FastAPI application
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Determine mode
        if db_manager:
            # Library mode: use provided database
            app.state.db = db_manager
            app.state.external_db = True
            app.state.schema = schema or "my_service"
        else:
            # Standalone mode: create own connection
            from .config import Settings
            from .database import Database

            settings = Settings(**(config or {}))
            db = Database(
                settings.database_url,
                schema=schema or settings.database_schema,
            )
            await db.connect()
            app.state.db = db.db
            app.state.external_db = False
            app.state.schema = db.schema

        # Always run migrations if requested
        if run_migrations:
            migrations_path = Path(__file__).parent / "migrations"
            migrations = AsyncMigrationManager(
                app.state.db,
                migrations_path=str(migrations_path),
                module_name=f"my_service_{app.state.schema}"
            )
            result = await migrations.apply_pending_migrations()

            if result.get("applied"):
                logger.info(f"Applied {len(result['applied'])} migrations")

        try:
            yield
        finally:
            # Only disconnect if we created the connection
            if not app.state.external_db:
                await app.state.db.disconnect()

    # Create app
    app = FastAPI(
        title="My Service",
        lifespan=lifespan,
    )

    # Add routes
    from .routers import items, users
    app.include_router(items.router)
    app.include_router(users.router)

    return app

# Default app for standalone mode (backward compatible)
app = create_app()
```

### Using as a Library

```python
# parent_app/main.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pgdbm import AsyncDatabaseManager, DatabaseConfig
from my_service import create_app as create_service_app

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage shared resources for parent app"""

    # Create shared database connection
    config = DatabaseConfig(
        connection_string="postgresql://localhost/parent_app",
        min_connections=50,  # Shared pool
        max_connections=100
    )
    db = AsyncDatabaseManager(config)
    await db.connect()

    # Create service apps with different schemas
    service1 = create_service_app(
        db_manager=db,
        schema="service1",
        run_migrations=True
    )

    service2 = create_service_app(
        db_manager=db,
        schema="service2",
        run_migrations=True
    )

    # Store for access
    app.state.db = db
    app.state.service1 = service1
    app.state.service2 = service2

    try:
        yield
    finally:
        await db.disconnect()

# Parent app
app = FastAPI(lifespan=lifespan)

# Mount service apps
app.mount("/service1", app.state.service1)
app.mount("/service2", app.state.service2)

# Add parent-specific routes
@app.get("/")
async def root():
    return {"services": ["service1", "service2"]}
```

### Testing Strategy

Test both modes using parametrized fixtures:

```python
# tests/conftest.py
import pytest
import pytest_asyncio
from pgdbm.fixtures.conftest import test_db_factory

@pytest_asyncio.fixture(params=["standalone", "library"])
async def service_app(request, test_db_factory):
    """Test service in both modes"""
    mode = request.param

    if mode == "standalone":
        # Test standalone mode
        from my_service import create_app
        app = create_app()
    else:
        # Test library mode with external db
        from my_service import create_app
        db = await test_db_factory.create_db(suffix="service", schema="test")
        app = create_app(db_manager=db)

    # Provide test client
    from httpx import AsyncClient, ASGITransport
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, mode

# Usage in tests
async def test_service_endpoint(service_app):
    client, mode = service_app
    response = await client.get("/items")
    assert response.status_code == 200
    # Test works in both modes!
```

### Module Configuration with pgdbm CLI

Use `pgdbm.toml` to configure multi-module applications:

```toml
[project]
name = "my_platform"
default_env = "dev"

[environments.dev]
url = "postgresql://localhost/platform_dev"
schema = "public"

# Module configuration
[modules.my_service]
migrations_path = "src/my_service/migrations"
schema = "my_service"
mode = "dual"  # standalone | library | dual
depends_on = []

[modules.extended_service]
migrations_path = "src/extended_service/migrations"
schema = "extended_service"
depends_on = ["my_service"]  # Migration dependencies
mode = "library"  # Always needs parent app

# Shared pool configuration (for integrated mode)
[shared_pool]
min_connections = 50
max_connections = 100
modules = ["my_service", "extended_service"]
```

Apply migrations with dependency resolution:

```bash
# Apply all modules in dependency order
pgdbm migrate apply --all

# Output:
# Resolved module order: my_service → extended_service
# ✓ my_service: 001_initial.sql
# ✓ extended_service: 001_extensions.sql
```

### Best Practices

1. **Always Support Both Modes**
   - Accept optional `db_manager` parameter
   - Create connection only if not provided
   - Clean up only what you created

2. **Use Unique Module Names**
   ```python
   # Include schema in module name to prevent conflicts
   module_name = f"{service_name}_{schema}"
   ```

3. **Document Mode Requirements**
   ```python
   class MyService:
       """Service supporting dual-mode operation.

       Standalone mode:
           service = MyService(connection_string="postgresql://...")

       Library mode:
           service = MyService(db_manager=shared_db)
       """
   ```

4. **Test Both Modes**
   - Parametrize tests to run in both configurations
   - Verify migrations work in both modes
   - Check resource cleanup

5. **Provide Clear CLI**
   ```bash
   # Standalone operations
   my-service serve
   my-service db migrate
   my-service db create

   # Library mode documented in code
   ```

### Common Pitfalls

1. **Hardcoded Connections**
   ```python
   # ❌ Bad: Always creates connection
   class Service:
       def __init__(self):
           self.db = create_connection()

   # ✅ Good: Accepts external connection
   class Service:
       def __init__(self, db=None):
           self.db = db or create_connection()
   ```

2. **Schema Conflicts**
   ```python
   # ❌ Bad: Hardcoded schema
   migrations = AsyncMigrationManager(db, module_name="service")

   # ✅ Good: Schema-aware module name
   migrations = AsyncMigrationManager(db, module_name=f"service_{schema}")
   ```

3. **Missing Cleanup**
   ```python
   # ❌ Bad: Always disconnects
   async def shutdown():
       await db.disconnect()

   # ✅ Good: Conditional cleanup
   async def shutdown():
       if not self.external_db:
           await db.disconnect()
   ```

### Real-World Example: llmring-server

The llmring project demonstrates this pattern:

- **llmring-server**: Core service with dual-mode support
- **llmring-api**: Extends server using library mode
- **llmring-cli**: Uses server as library for client operations

This architecture allows:
- Independent deployment of server
- Extended functionality in API
- Shared connection pools
- Consistent migration management
- Easy testing of all components

## Pattern 3: Shared Pool Application (Consumer)

Use this when multiple services share one database with schema isolation.

### When to Use

- Monolithic apps with modular services
- Resource-constrained environments
- Multi-tenant SaaS applications
- Migrating from monolith to microservices

### Implementation

```python
from pgdbm import AsyncDatabaseManager, DatabaseConfig

class Application:
    def __init__(self):
        self.shared_pool = None
        self.services = {}

    async def initialize(self):
        # Create shared pool with total connections
        config = DatabaseConfig(
            connection_string="postgresql://localhost/app",
            min_connections=50,   # Total for ALL services
            max_connections=100   # Monitor usage!
        )
        self.shared_pool = await AsyncDatabaseManager.create_shared_pool(config)

        # Create schema-isolated managers
        user_db = AsyncDatabaseManager(pool=self.shared_pool, schema="users")
        order_db = AsyncDatabaseManager(pool=self.shared_pool, schema="orders")
        billing_db = AsyncDatabaseManager(pool=self.shared_pool, schema="billing")

        # Initialize services with their managers
        self.services['users'] = UserService(db_manager=user_db)
        self.services['orders'] = OrderService(db_manager=order_db)
        self.services['billing'] = BillingService(db_manager=billing_db)

        # Each service runs its own migrations
        for service in self.services.values():
            await service.initialize()

    async def shutdown(self):
        # Shutdown services first
        for service in self.services.values():
            await service.close()

        # Then close shared pool
        if self.shared_pool:
            await self.shared_pool.close()
```

### Schema Isolation

Each service gets its own schema to prevent conflicts:

```
Database: app
├── Schema: public
│   └── schema_migrations (shared)
├── Schema: users
│   ├── users table
│   └── profiles table
├── Schema: orders
│   ├── orders table
│   └── order_items table
└── Schema: billing
    ├── invoices table
    └── payments table
```

### Pool Sizing

Calculate pool size based on service needs:

```python
# Estimate PEAK concurrent connections per service
services = [
    ("users", 10),     # High traffic
    ("orders", 15),    # Very high traffic
    ("billing", 5),    # Low traffic
    ("analytics", 10), # Periodic jobs
]

# Calculate pool size (shared pool totals cover ALL services)
peak = sum(s[1] for s in services)                 # 40
buffer = int(peak * 0.25)                          # 10

# PostgreSQL has a hard max_connections limit; reserve some for migrations/admin/psql.
db_max_connections = 200
reserved = 40

max_connections = min(peak + buffer, db_max_connections - reserved)  # 50
# min_connections is a FLOOR (connections opened eagerly). Keep it low unless you have steady load.
min_connections = min(5, max_connections)  # 5
```

### Monitoring

Track pool usage to detect issues:

```python
async def monitor_pool_health(db):
    stats = await db.get_pool_stats()

    usage = stats['used_size'] / stats['size']
    if usage > 0.8:
        logger.warning(f"High pool usage: {usage:.1%}")

    return {
        "total_connections": stats['size'],
        "active_connections": stats['used_size'],
        "idle_connections": stats['free_size'],
        "usage_percent": usage * 100
    }
```

## Security and Reliability Defaults

### TLS/SSL

Enable TLS and enforce certificate verification for production deployments:

```python
config = DatabaseConfig(
    connection_string="postgresql://db.example.com/app",
    ssl_enabled=True,
    ssl_mode="verify-full",        # 'require' | 'verify-ca' | 'verify-full'
    ssl_ca_file="/etc/ssl/certs/ca.pem",
)
db = AsyncDatabaseManager(config)
await db.connect()
```

Guidance:
- Use `verify-full` whenever possible.
- If you terminate TLS at a proxy, ensure the upstream to Postgres is secured and access-controlled.

### Statement and Session Timeouts

Prevent runaway queries and stuck transactions with server-side timeouts (milliseconds):

```python
config = DatabaseConfig(
    statement_timeout_ms=60_000,
    idle_in_transaction_session_timeout_ms=60_000,
    lock_timeout_ms=5_000,
)
```

These default to sane values; set to `None` to disable or override explicitly in `server_settings`.

### Cross-Schema Limitations

PostgreSQL foreign keys cannot cross schemas. Handle references in application code:

```python
# Can't use foreign keys between schemas
# user_id INTEGER REFERENCES users.users(id)  -- Won't work!

# Instead, validate in application:
async def create_order(self, user_id: UUID):
    # Validate user exists in users schema
    user = await self.user_service.get_user(user_id)
    if not user:
        raise ValueError("User not found")

    return await self.db.fetch_one("""
        INSERT INTO {{tables.orders}} (user_id, total)
        VALUES ($1, $2)
        RETURNING *
    """, user_id, total)
```

### Shared Tables Pattern

Some tables might be truly shared across services (in public schema):

```sql
-- migrations/001_shared.sql
-- Don't use {{tables.}} for truly shared tables
CREATE TABLE IF NOT EXISTS service_registry (
    service_name VARCHAR(100) PRIMARY KEY,
    service_url VARCHAR(255) NOT NULL,
    healthy BOOLEAN DEFAULT true
);
```

### Pros and Cons

✅ **Pros:**
- Efficient connection usage
- Centralized configuration
- Easy service coordination
- Good for transitional architectures
- Minimal schema overhead (PostgreSQL handles efficiently)

❌ **Cons:**
- Single point of failure
- Services affect each other
- Complex pool sizing
- Harder to scale individual services
- No foreign keys across schemas

## Decision Matrix

| Factor | Standalone | Library | Shared Pool |
|--------|-----------|---------|-------------|
| **Complexity** | Low | Medium | High |
| **Flexibility** | High | High | Medium |
| **Resource Usage** | High | Varies | Low |
| **Isolation** | Complete | Depends | Schema-only |
| **Scaling** | Independent | Depends | Together |
| **Best For** | Microservices | Packages | Monoliths |

## Common Mistakes to Avoid

### 1. Forgetting {{tables.}} Syntax

❌ **Wrong:**
```sql
CREATE TABLE users (...);
CREATE TABLE orders (
    user_id INT REFERENCES users(id)
);
```

✅ **Right:**
```sql
CREATE TABLE {{tables.users}} (...);
CREATE TABLE {{tables.orders}} (
    user_id INT REFERENCES {{tables.users}}(id)
);
```

### 2. Not Using module_name

❌ **Wrong:**
```python
# All migrations go to default module
migrations = AsyncMigrationManager(db, "./migrations")
```

✅ **Right:**
```python
# Isolated by module name
migrations = AsyncMigrationManager(
    db,
    "./migrations",
    module_name="my_service"
)
```

### 3. Incorrect Library Initialization

❌ **Wrong:**
```python
class MyLibrary:
    async def initialize(self):
        if self._external_db:
            return  # Skip everything!
```

✅ **Right:**
```python
class MyLibrary:
    async def initialize(self):
        # Always run migrations regardless of db source
        migrations = AsyncMigrationManager(...)
        await migrations.apply_pending_migrations()
```

### 4. Mixed Schema References

❌ **Wrong:**
```sql
-- Mixing styles causes confusion
CREATE TABLE {{tables.users}} (...);
CREATE TABLE public.audit_log (...);
INSERT INTO myschema.users ...;
```

✅ **Right:**
```sql
-- Consistent use of templates
CREATE TABLE {{tables.users}} (...);
CREATE TABLE {{tables.audit_log}} (...);
INSERT INTO {{tables.users}} ...;
```

## Real-World Example: E-commerce Platform

Here's how an e-commerce platform might use these patterns:

```python
# Main application (Pattern 3: Shared Pool)
class EcommercePlatform:
    async def initialize(self):
        # Shared pool for core services
        self.pool = await AsyncDatabaseManager.create_shared_pool(config)

        # Core services with schema isolation
        catalog_db = AsyncDatabaseManager(pool=self.pool, schema="catalog")
        order_db = AsyncDatabaseManager(pool=self.pool, schema="orders")
        user_db = AsyncDatabaseManager(pool=self.pool, schema="users")

        # Initialize services
        self.catalog = CatalogService(db_manager=catalog_db)
        self.orders = OrderService(db_manager=order_db)
        self.users = UserService(db_manager=user_db)

        # External library (Pattern 2: Reusable Library)
        # This could be memory-service for search
        memory_db = AsyncDatabaseManager(pool=self.pool, schema="memory")
        self.search = MemoryService(db_manager=memory_db)

        # Analytics runs separately (Pattern 1: Standalone)
        # It has its own database for isolation
        self.analytics = AnalyticsService(
            connection_string="postgresql://localhost/analytics"
        )
```

## Framework Integration Example

Here's how to integrate pgdbm with FastAPI using the shared pool pattern:

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
from pgdbm import AsyncDatabaseManager, DatabaseConfig

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create shared pool
    config = DatabaseConfig(
        connection_string="postgresql://localhost/app",
        min_connections=50,
        max_connections=100
    )
    shared_pool = await AsyncDatabaseManager.create_shared_pool(config)

    # Create schema-isolated managers
    app.state.user_db = AsyncDatabaseManager(pool=shared_pool, schema="users")
    app.state.order_db = AsyncDatabaseManager(pool=shared_pool, schema="orders")

    yield

    # Shutdown: Close shared pool
    await shared_pool.close()

app = FastAPI(lifespan=lifespan)

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    return await app.state.user_db.fetch_one(
        "SELECT * FROM {{tables.users}} WHERE id = $1",
        user_id
    )
```

This pattern ensures proper resource management and schema isolation for web applications.

## Summary

- **Use Standalone** when services are independent
- **Use Library pattern** when building reusable components
- **Use Shared Pool** when services are tightly coupled
- **Always use {{tables.}}** syntax in migrations
- **Always specify module_name** for migration isolation
- **Libraries should always run their own migrations**

Remember: The pattern you choose affects scalability, resource usage, and operational complexity. Start simple and evolve as needed.
