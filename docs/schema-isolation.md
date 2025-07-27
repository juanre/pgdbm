# Schema Isolation Guide

This guide explains how to use PostgreSQL schemas to isolate tables for different services or modules sharing the same database.

## Overview

Schema isolation allows multiple services or modules to:
- Share a single database connection pool
- Have their own namespaced tables (no naming conflicts)
- Maintain independent migrations
- Achieve better resource utilization

## Basic Usage

### 1. Create Schema-Isolated Database Manager

```python
from pgdbm import AsyncDatabaseManager, DatabaseConfig

# Option 1: Create with schema in config
config = DatabaseConfig(
    host="localhost",
    database="myapp",
    schema="user_service"  # Tables will be in user_service schema
)
db = AsyncDatabaseManager(config)

# Option 2: Share pool with different schemas
shared_pool = await AsyncDatabaseManager.create_shared_pool(config)

user_db = AsyncDatabaseManager(pool=shared_pool, schema="users")
order_db = AsyncDatabaseManager(pool=shared_pool, schema="orders")
```

### 2. Write Schema-Aware Migrations

Use the `{{tables.tablename}}` syntax in your migrations:

```sql
-- migrations/001_users.sql
CREATE TABLE IF NOT EXISTS {{tables.users}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- This will create:
-- users.users (if schema is "users")
-- public.users (if no schema specified)
```

### 3. Query with Automatic Schema Resolution

```python
# The {{tables.}} syntax is automatically replaced
result = await db.fetch_one(
    "SELECT * FROM {{tables.users}} WHERE email = $1",
    "user@example.com"
)

# Expands to: SELECT * FROM users.users WHERE email = $1
```

## Complete Example: Microservices

Here's how multiple services can share a database:

### Shared Database Manager

```python
# shared/database.py
class SharedDatabaseManager:
    _instance = None
    _pool = None

    async def initialize(self):
        config = DatabaseConfig(connection_string=os.environ["DATABASE_URL"])
        # Create shared pool
        self._pool = await AsyncDatabaseManager.create_shared_pool(config)
        # Create manager for shared operations
        self._db_manager = AsyncDatabaseManager(pool=self._pool)

    def get_pool(self):
        return self._pool

# Base class for services
class ServiceDatabase:
    def __init__(self, service_name: str, schema_name: str):
        self.service_name = service_name
        self.schema_name = schema_name
        self.db = None

    async def initialize(self):
        shared = await SharedDatabaseManager.get_instance()
        # Create schema-isolated manager using shared pool
        self.db = AsyncDatabaseManager(
            pool=shared.get_pool(),
            schema=self.schema_name
        )

        # Create schema
        await shared._db_manager.execute(
            f'CREATE SCHEMA IF NOT EXISTS "{self.schema_name}"'
        )

        # Run service-specific migrations
        migrations = AsyncMigrationManager(
            self.db,
            migrations_path=f"./services/{self.schema_name}/migrations",
            module_name=self.schema_name
        )
        await migrations.apply_pending()
```

### User Service

```python
# services/users/db.py
class UserDatabase(ServiceDatabase):
    def __init__(self):
        super().__init__("user-service", "users")

    async def create_user(self, email: str, name: str):
        return await self.db.fetch_one("""
            INSERT INTO {{tables.users}} (email, name)
            VALUES ($1, $2)
            RETURNING *
        """, email, name)
```

```sql
-- services/users/migrations/001_users.sql
CREATE TABLE IF NOT EXISTS {{tables.users}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

### Order Service

```python
# services/orders/db.py
class OrderDatabase(ServiceDatabase):
    def __init__(self):
        super().__init__("order-service", "orders")

    async def create_order(self, user_id: UUID, items: List[dict]):
        return await self.db.fetch_one("""
            INSERT INTO {{tables.orders}} (user_id, items, total)
            VALUES ($1, $2, $3)
            RETURNING *
        """, user_id, items, calculate_total(items))
```

## Template Syntax Reference

### {{tables.tablename}}
- Expands to: `schema.tablename` (or just `tablename` if no schema)
- Use for: Table references in queries
- Example: `SELECT * FROM {{tables.users}}`

### {{schema}}
- Expands to: The schema name (or nothing if no schema)
- Use for: Schema-specific functions or types
- Example: `CREATE TYPE {{schema}}.order_status AS ENUM (...)`

## Best Practices

### 1. Use Module Names for Schemas

```python
# Good: Clear service boundaries
user_db = AsyncDatabaseManager(schema="users")
order_db = AsyncDatabaseManager(schema="orders")

# Avoid: Generic names
db1 = AsyncDatabaseManager(schema="schema1")
db2 = AsyncDatabaseManager(schema="schema2")
```

### 2. Separate Migrations by Service

```
services/
├── users/
│   └── migrations/
│       ├── 001_initial.sql
│       └── 002_add_profile.sql
├── orders/
│   └── migrations/
│       ├── 001_initial.sql
│       └── 002_add_shipping.sql
```

### 3. Handle Cross-Schema References

Since foreign keys can't cross schemas, use application-level validation:

```python
async def create_order(self, user_id: UUID):
    # Validate user exists (can't use FK constraint)
    user = await user_service.get_user(user_id)
    if not user:
        raise ValueError("User not found")

    # Create order
    return await self.db.fetch_one("""
        INSERT INTO {{tables.orders}} (user_id, ...)
        VALUES ($1, ...)
        RETURNING *
    """, user_id)
```

### 4. Use Shared Tables Sparingly

Some tables might be truly shared (in public schema):

```sql
-- migrations/001_shared.sql
-- These don't use {{tables.}} prefix
CREATE TABLE IF NOT EXISTS service_registry (
    service_name VARCHAR(100) PRIMARY KEY,
    service_url VARCHAR(255) NOT NULL
);
```

## Performance Considerations

1. **Connection Pool Sizing**: Size based on total services, not per-service
2. **Schema Overhead**: Minimal - PostgreSQL handles schemas efficiently
3. **Query Planning**: Schema-qualified names can improve query planning

## Troubleshooting

### "relation does not exist" errors

Check that:
1. Schema exists: `CREATE SCHEMA IF NOT EXISTS "schema_name"`
2. Migrations ran: Check `schema_migration_history` table
3. Using {{tables.}} syntax in queries

### Migration conflicts

Each service should use a unique `module_name`:

```python
migrations = AsyncMigrationManager(
    db,
    migrations_path="./migrations",
    module_name="user_service"  # Unique per service
)
```

## See Also

- [Migration Guide](migrations.md) - Details on migration management
- [API Reference](api-reference.md) - Complete API documentation
- [Examples](../examples/microservices/) - Complete microservices example
