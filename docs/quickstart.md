# Quick Start Guide

This guide gets you running with pgdbm in 5 minutes.

## Prerequisites

- Python 3.9+
- PostgreSQL 12+
- Basic async/await knowledge

## Installation

```bash
# Install using uv (recommended)
uv add pgdbm

# Or using pip
pip install pgdbm
```

## Basic Example

### 1. Create your migration file

Create a `migrations/` directory with your schema:

```sql
-- migrations/001_initial.sql
CREATE TABLE IF NOT EXISTS {{tables.users}} (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_email ON {{tables.users}}(email);
```

**Important**: The `{{tables.users}}` syntax is what makes your code reusable:
- Standalone: `{{tables.users}}` → `users`
- With schema isolation: `{{tables.users}}` → `myapp.users`

This template syntax is replaced at query execution time, allowing the same migration file to work in different deployment contexts.

### 2. Write your application

```python
import asyncio
from pgdbm import AsyncDatabaseManager, DatabaseConfig, AsyncMigrationManager

async def main():
    # Configure connection
    config = DatabaseConfig(
        host="localhost",
        database="myapp",
        user="postgres",
        password="postgres"
    )

    # Connect
    db = AsyncDatabaseManager(config)
    await db.connect()

    try:
        # Apply migrations
        migrations = AsyncMigrationManager(db, migrations_path="./migrations")
        result = await migrations.apply_pending_migrations()
        print(f"Applied {len(result['applied'])} migrations")

        # Use your database
        user_id = await db.execute_and_return_id(
            "INSERT INTO {{tables.users}} (email, name) VALUES ($1, $2)",
            "alice@example.com",
            "Alice Smith"
        )
        print(f"Created user {user_id}")

        # Query data
        users = await db.fetch_all("SELECT * FROM {{tables.users}}")
        for user in users:
            print(f"User: {user['name']} ({user['email']})")

    finally:
        await db.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
```

## Building Reusable Libraries

When building a library that uses pgdbm, follow this pattern. The goal is that the same module can:
- run standalone and own its database, or
- run inside another app and use its database, while always owning its schema and migrations.

```python
from pgdbm import AsyncDatabaseManager, DatabaseConfig, AsyncMigrationManager
from typing import Optional
from pathlib import Path

class MyLibrary:
    """A reusable library with database support."""

    def __init__(self,
                 connection_string: Optional[str] = None,
                 db_manager: Optional[AsyncDatabaseManager] = None):
        # Support both standalone (owner) and shared pool (consumer) modes
        if not connection_string and not db_manager:
            raise ValueError("Either connection_string or db_manager required")

        self._external_db = db_manager is not None
        self.db = db_manager
        self._connection_string = connection_string

    async def initialize(self):
        """Initialize the library and its database schema."""
        # Create connection if not provided
        if not self._external_db:
            config = DatabaseConfig(connection_string=self._connection_string)
            self.db = AsyncDatabaseManager(config)
            await self.db.connect()

        # CRITICAL: Always run your migrations with a unique module_name
        migrations = AsyncMigrationManager(
            self.db,
            migrations_path=Path(__file__).parent / "migrations",
            module_name="my_library"  # This prevents conflicts!
        )
        await migrations.apply_pending_migrations()

    async def create_user(self, email: str, name: str) -> int:
        """Create a user using our module's table."""
        return await self.db.execute_and_return_id(
            "INSERT INTO {{tables.users}} (email, name) VALUES ($1, $2)",
            email, name
        )

    async def close(self):
        """Cleanup if we own the connection."""
        if self.db and not self._external_db:
            await self.db.disconnect()
```

### Using modules together

Multiple modules can share a database without conflicts (schema isolation + per-module migrations):

```python
# Each module gets its own schema
config = DatabaseConfig(connection_string="postgresql://localhost/app")
shared_pool = await AsyncDatabaseManager.create_shared_pool(config)

# Create isolated database managers
user_db = AsyncDatabaseManager(pool=shared_pool, schema="users")
blog_db = AsyncDatabaseManager(pool=shared_pool, schema="blog")

# Initialize modules
user_module = UserModule(db_manager=user_db)
blog_module = BlogModule(db_manager=blog_db)

# Both can have a "users" table without conflict:
# - users.users (user module's table)
# - blog.users (blog module's table)

Tip: In shared mode, each module still runs its own migrations against its schema using its own `module_name`.
```

## Migration Files Best Practices

1. **Number your migrations**: Use prefixes like `001_`, `002_` for ordering
2. **Use templates**: `{{tables.tablename}}` for schema-aware tables
3. **One change per file**: Makes rollbacks easier to reason about
4. **Include indexes**: Don't forget performance-critical indexes

Example migration sequence:

```
migrations/
├── 001_users.sql          # Core user tables
├── 002_user_indexes.sql   # Performance indexes
├── 003_user_profiles.sql  # Extended features
└── 004_user_settings.sql  # Additional tables
```

## Testing

pgdbm includes testing utilities:

```python
# conftest.py
from pgdbm.fixtures.conftest import *

# test_users.py
async def test_user_creation(test_db):
    # Test database with automatic cleanup
    user_module = UserModule(db_manager=test_db)
    await user_module.initialize()

    user_id = await user_module.create_user("test@example.com", "Test User")
    assert user_id > 0
```

## Key Concepts to Remember

1. **Template Syntax**: Always use `{{tables.tablename}}` in migrations and queries
2. **Module Names**: Always specify `module_name` in AsyncMigrationManager for libraries
3. **Schema Isolation**: Use schemas to separate different services' tables
4. **Migration Ownership**: Libraries should always run their own migrations

## Next Steps

- **[Patterns Guide](patterns.md)** - Choose the right deployment pattern
- **[Migration Guide](migrations.md)** - Deep dive into migration system
- **[API Reference](api-reference.md)** - Complete API documentation

## Common Patterns

### Environment-based configuration

```python
import os
from pgdbm import DatabaseConfig

config = DatabaseConfig(
    host=os.getenv("DB_HOST", "localhost"),
    database=os.getenv("DB_NAME", "myapp"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASSWORD")  # Also checks DB_PASSWORD env var
)
```

### FastAPI Integration

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    config = DatabaseConfig.from_env()
    app.state.db = AsyncDatabaseManager(config)
    await app.state.db.connect()

    # Apply migrations
    migrations = AsyncMigrationManager(app.state.db, "./migrations")
    await migrations.apply_pending_migrations()

    yield

    # Shutdown
    await app.state.db.disconnect()

app = FastAPI(lifespan=lifespan)
```
