# Integration Patterns

This guide covers the two main patterns for using pgdbm in your applications.

## Pattern 1: Standalone Services

Each service manages its own database connections. Good for:
- Microservices
- Development and testing
- Services that can't share a database

```python
class UserService:
    def __init__(self):
        self.db = None

    async def initialize(self):
        config = DatabaseConfig(
            connection_string="postgresql://localhost/users",
            schema="users"
        )
        self.db = AsyncDatabaseManager(config)
        await self.db.connect()

        # Apply migrations
        migrations = AsyncMigrationManager(self.db, "./migrations")
        await migrations.apply_pending()

    async def shutdown(self):
        if self.db:
            await self.db.disconnect()
```

## Pattern 2: Shared Connection Pool

Multiple services share a single connection pool. Ideal for:
- Monolithic applications with modular services
- Resource-constrained environments
- Services sharing the same database

```python
# Application startup
async def setup_services():
    # Create shared pool
    config = DatabaseConfig(
        connection_string="postgresql://localhost/app",
        min_connections=50,   # Total for all services
        max_connections=100
    )
    shared_pool = await AsyncDatabaseManager.create_shared_pool(config)

    # Create service-specific managers with isolated schemas
    user_db = AsyncDatabaseManager(pool=shared_pool, schema="users")
    order_db = AsyncDatabaseManager(pool=shared_pool, schema="orders")
    billing_db = AsyncDatabaseManager(pool=shared_pool, schema="billing")

    # Initialize services with shared connections
    user_service = UserService(db_manager=user_db)
    order_service = OrderService(db_manager=order_db)
    billing_service = BillingService(db_manager=billing_db)

    return shared_pool, [user_service, order_service, billing_service]

# Service implementation
class UserService:
    def __init__(self, db_manager=None):
        self._external_db = db_manager is not None
        self.db = db_manager

    async def initialize(self):
        if not self._external_db:
            # Standalone mode
            config = DatabaseConfig(
                connection_string="postgresql://localhost/users",
                schema="users"
            )
            self.db = AsyncDatabaseManager(config)
            await self.db.connect()

        # Always apply migrations
        migrations = AsyncMigrationManager(self.db, "./migrations")
        await migrations.apply_pending()

    async def shutdown(self):
        # Only disconnect if we own the connection
        if self.db and not self._external_db:
            await self.db.disconnect()
```

## Web Framework Integration

### FastAPI

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    config = DatabaseConfig(connection_string="postgresql://localhost/app")
    shared_pool = await AsyncDatabaseManager.create_shared_pool(config)

    app.state.user_db = AsyncDatabaseManager(pool=shared_pool, schema="users")
    app.state.order_db = AsyncDatabaseManager(pool=shared_pool, schema="orders")

    yield

    # Shutdown
    await shared_pool.close()

app = FastAPI(lifespan=lifespan)

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    return await app.state.user_db.fetch_one(
        "SELECT * FROM {{tables.users}} WHERE id = $1",
        user_id
    )
```

### Flask/Quart

```python
from quart import Quart

app = Quart(__name__)

@app.before_serving
async def startup():
    config = DatabaseConfig(connection_string="postgresql://localhost/app")
    app.db = AsyncDatabaseManager(config)
    await app.db.connect()

@app.after_serving
async def shutdown():
    await app.db.disconnect()

@app.route("/users/<int:user_id>")
async def get_user(user_id):
    user = await app.db.fetch_one(
        "SELECT * FROM users WHERE id = $1",
        user_id
    )
    return user or ("Not found", 404)
```

## Connection Pool Sizing

### Standalone Services
- Each service: 10-20 connections
- Good isolation but uses more resources

### Shared Pool
- Total connections = sum of service minimums
- More efficient but requires coordination

```python
# Calculate pool size
services = [
    ("users", 10),    # Expected concurrent queries
    ("orders", 15),
    ("billing", 5),
]

min_connections = sum(s[1] for s in services)  # 30
max_connections = min_connections * 2           # 60
```

## Monitoring

```python
async def health_check(db: AsyncDatabaseManager):
    stats = await db.get_pool_stats()

    return {
        "pool_size": stats["size"],
        "active_connections": stats["used_size"],
        "idle_connections": stats["free_size"],
        "utilization": f"{stats['used_size'] / stats['size']:.1%}"
    }
```

## Best Practices

1. **Use shared pools** when services share a database
2. **Isolate with schemas** to prevent table conflicts
3. **Monitor pool usage** to detect sizing issues
4. **Apply migrations** during service initialization
5. **Handle cleanup** properly in shutdown hooks
