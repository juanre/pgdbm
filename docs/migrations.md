# Migration Guide

This guide covers database migration patterns using pgdbm.

## Overview

The migration system provides:
- Checksum-based change tracking
- Module-specific migrations
- Dry-run support
- Migration history
- Rollback recording

## Migration Setup

### Directory Structure

Each module typically has its own migrations directory:

```
# Main application
app/
├── migrations/
│   ├── 001_initial_schema.sql
│   ├── 002_add_users_table.sql
│   └── 003_add_indexes.sql

# Auth module
auth_module/
├── migrations/
│   ├── 001_auth_tables.sql
│   └── 002_auth_indexes.sql

# Billing library
billing_lib/
├── migrations/
│   └── 001_billing_tables.sql
```

### Basic Usage

```python
from pgdbm import AsyncMigrationManager

# Create migration manager
migrations = AsyncMigrationManager(db, migrations_path="./migrations")

# Apply all pending migrations
result = await migrations.apply_pending_migrations()
for migration in result["applied"]:
    print(f"Applied: {migration['filename']} in {migration['execution_time_ms']}ms")
```

## Writing Migrations

### Migration Naming and Versioning

pgdbm automatically extracts version numbers from migration filenames to ensure proper ordering. Supported patterns:

1. **Numeric Prefix** (Recommended)
   - `001_initial_schema.sql` → version "001"
   - `002_add_users.sql` → version "002"
   - Allows for clear ordering and gaps for future migrations

2. **Flyway Style**
   - `V1__initial_schema.sql` → version "1"
   - `V2__add_users.sql` → version "2"
   - Compatible with Flyway migration tool

3. **Timestamp Prefix**
   - `20240126120000_initial_schema.sql` → version "20240126120000"
   - `20240127093015_add_users.sql` → version "20240127093015"
   - Prevents conflicts in team environments

4. **Custom Names**
   - If no pattern matches, the entire filename (minus .sql) is used as version
   - Not recommended as it may lead to unexpected ordering

### Migration File Format

```sql
-- migrations/001_initial_schema.sql
-- Description: Create initial schema and tables

CREATE TABLE IF NOT EXISTS {{tables.users}} (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS {{tables.sessions}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER REFERENCES {{tables.users}}(id) ON DELETE CASCADE,
    expires_at TIMESTAMP NOT NULL
);

CREATE INDEX idx_sessions_user_id ON {{tables.sessions}}(user_id);
CREATE INDEX idx_sessions_expires ON {{tables.sessions}}(expires_at);
```

## Template Syntax for Schema Isolation

pgdbm provides a template syntax that enables your migrations and queries to work in different deployment contexts.

### The {{tables.}} Syntax

The `{{tables.tablename}}` placeholder is replaced at query execution time with the appropriate schema-qualified table name:

```sql
-- In your migration file:
CREATE TABLE IF NOT EXISTS {{tables.users}} (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL
);

-- At runtime, this becomes:
-- Standalone mode: CREATE TABLE IF NOT EXISTS users (...)
-- With schema "myapp": CREATE TABLE IF NOT EXISTS myapp.users (...)
```

### Where to Use Templates

Templates work in ALL SQL contexts:

```sql
-- Creating tables
CREATE TABLE IF NOT EXISTS {{tables.documents}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id TEXT NOT NULL
);

-- Foreign key references
CREATE TABLE IF NOT EXISTS {{tables.document_chunks}} (
    chunk_id UUID PRIMARY KEY,
    document_id UUID REFERENCES {{tables.documents}}(id) ON DELETE CASCADE
);

-- Indexes
CREATE INDEX idx_documents_owner ON {{tables.documents}}(owner_id);

-- Functions
CREATE OR REPLACE FUNCTION get_document_count()
RETURNS INTEGER AS $$
BEGIN
    RETURN (SELECT COUNT(*) FROM {{tables.documents}});
END;
$$ LANGUAGE plpgsql;

-- Even in complex queries
WITH recent_docs AS (
    SELECT * FROM {{tables.documents}}
    WHERE created_at > NOW() - INTERVAL '7 days'
)
SELECT u.*, COUNT(d.id) as doc_count
FROM {{tables.users}} u
LEFT JOIN recent_docs d ON u.id = d.owner_id
GROUP BY u.id;
```

### When Templates Are Replaced

**Important**: Templates are replaced at query execution time, NOT when migrations are stored:

1. Migration files keep the `{{tables.}}` syntax as-is
2. When a query runs, pgdbm replaces templates based on the current schema context
3. This allows the same migration files to work in different schemas

### Schema Context Behavior

The replacement depends on how the AsyncDatabaseManager was created:

```python
# Standalone - no schema prefix
db = AsyncDatabaseManager(config)
# {{tables.users}} → users

# With explicit schema (owned pool)
config = DatabaseConfig(connection_string="postgresql://localhost/myapp", schema="myapp")
db = AsyncDatabaseManager(config)
# {{tables.users}} → myapp.users

# Shared pool with schema
pool = await AsyncDatabaseManager.create_shared_pool(config)
db = AsyncDatabaseManager(pool=pool, schema="myapp")
# {{tables.users}} → myapp.users
```

### Direct {{schema}} Syntax

The `{{schema}}` placeholder is used for PostgreSQL objects that require explicit schema qualification:

```sql
-- Creating functions in the schema
CREATE OR REPLACE FUNCTION {{schema}}.update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Creating types in the schema
CREATE TYPE {{schema}}.order_status AS ENUM ('pending', 'confirmed', 'shipped');

-- Referencing schema-qualified types
CREATE TABLE IF NOT EXISTS {{tables.orders}} (
    id SERIAL PRIMARY KEY,
    status {{schema}}.order_status NOT NULL DEFAULT 'pending'
);
```

Use `{{schema}}` for:
- Function definitions
- Type (ENUM, composite) definitions
- Stored procedures
- Views that need schema qualification

Use `{{tables.tablename}}` for:
- Table references in CREATE TABLE, ALTER TABLE
- Foreign key references
- Index creation
- Queries (SELECT, INSERT, UPDATE, DELETE)

## Migration Tracking

pgdbm tracks migrations in a `schema_migrations` table. By default the table is created in the same schema configured for the `AsyncDatabaseManager` (if a schema is set), otherwise in `public`.

Note: The docs use `{{schema}}`/`{{tables.*}}` as placeholders to indicate schema-aware resolution at runtime. The actual SQL executed will be schema-qualified appropriately based on the manager’s configuration. For example, with `schema="myapp"`, the table will be created as `"myapp".schema_migrations`; without a schema it will be created in `public`.

### The module_name Parameter

The `module_name` parameter enables multiple applications or libraries to share the same database. Each module's records are isolated via the `module_name` column and the per-schema placement of the tracking table when a schema is configured:

```python
# Default: uses schema name or "default"
migrations = AsyncMigrationManager(db)

# Explicit module name for isolation
migrations = AsyncMigrationManager(
    db,
    migrations_path="./my_lib/migrations",
    module_name="my_library"
)
```

The **UNIQUE(filename, module_name)** constraint means different modules can have identically named migration files without conflicts. Each module tracks its own migration history independently.

### Example: Multiple Modules

```python
# Auth module specifies its own migrations directory
auth_migrations = AsyncMigrationManager(
    db,
    migrations_path="./auth_module/migrations",
    module_name="auth"
)

# Billing library has its own migrations
billing_migrations = AsyncMigrationManager(
    db,
    migrations_path="./billing_lib/migrations",
    module_name="billing"
)

# Both can have "001_initial.sql" without conflict!
# Each looks only in its own migrations_path directory
```

## Migration Operations

### Dry Run

Test migrations without applying:

```python
# See what would be applied
pending = await migrations.get_pending_migrations()
print(f"Would apply {len(pending)} migrations:")
for migration in pending:
    print(f"  - {migration.filename}")

# Dry run execution
results = await migrations.apply_pending_migrations(dry_run=True)
# No changes made to database
```

### Check Migration Status

```python
# Get migration history
history = await migrations.get_migration_history()
for record in history:
    print(f"{record.filename}: applied at {record.applied_at}")

# Check specific migration
is_applied = await migrations.is_migration_applied("001_initial_schema.sql")

# Access migration details
pending = await migrations.get_pending_migrations()
for migration in pending:
    print(f"Version: {migration.version}, File: {migration.filename}")
    # version property extracts from filename automatically
```

### Create New Migration

```python
# Generate migration file
content = """
CREATE TABLE IF NOT EXISTS {{tables.products}} (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    price DECIMAL(10, 2) NOT NULL
);
"""

filename = await migrations.create_migration(
    name="add_products_table",
    content=content
)
print(f"Created migration: {filename}")
```

## Error Handling

### Failed Migrations

```python
try:
    await migrations.apply_pending_migrations()
except Exception as e:
    # Check which migrations succeeded
    history = await migrations.get_migration_history()
    last_success = history[-1] if history else None

    print(f"Migration failed at: {e}")
    if last_success:
        print(f"Last successful: {last_success.filename}")
```

### Rollback Records

Record rollback SQL for critical migrations:

```python
# Record how to undo a migration
await migrations.rollback_migration_record(
    migration_id=migration.id,
    rollback_sql="DROP TABLE products;"
)

# Get rollback SQL if needed
rollback = await db.fetch_one(
    "SELECT rollback_sql FROM migration_history WHERE id = $1",
    migration_id
)
```

## Best Practices

### 1. One Change Per Migration

Keep migrations focused:

```sql
-- Good: Single responsibility
-- 004_add_user_status.sql
ALTER TABLE {{tables.users}} ADD COLUMN status VARCHAR(20) DEFAULT 'active';

-- Bad: Multiple unrelated changes
-- 004_various_changes.sql
ALTER TABLE {{tables.users}} ADD COLUMN status VARCHAR(20);
CREATE TABLE {{tables.products}} (...);
ALTER TABLE {{tables.orders}} ADD COLUMN discount DECIMAL;
```

### 2. Idempotent Migrations

Make migrations safe to run multiple times:

```sql
-- Good: Idempotent
CREATE TABLE IF NOT EXISTS {{tables.users}} (...);
CREATE INDEX IF NOT EXISTS idx_users_email ON {{tables.users}}(email);

-- Bad: Will fail if run twice
CREATE TABLE {{tables.users}} (...);
CREATE INDEX idx_users_email ON {{tables.users}}(email);
```

### 3. Backward Compatible Changes

Avoid breaking existing code:

```sql
-- Good: Add nullable column
ALTER TABLE {{tables.users}} ADD COLUMN phone VARCHAR(20);

-- Later migration after code deployed
ALTER TABLE {{tables.users}} ALTER COLUMN phone SET NOT NULL;

-- Bad: Immediate breaking change
ALTER TABLE {{tables.users}} ADD COLUMN phone VARCHAR(20) NOT NULL;
```

### 4. Data Migrations

Handle data transformations carefully:

```sql
-- Add new column
ALTER TABLE {{tables.users}} ADD COLUMN full_name VARCHAR(255);

-- Populate from existing data
UPDATE {{tables.users}}
SET full_name = CONCAT(first_name, ' ', last_name)
WHERE full_name IS NULL;

-- Only then make it required
ALTER TABLE {{tables.users}} ALTER COLUMN full_name SET NOT NULL;
```

## Integration Example

```python
# app/migrations.py
import asyncio
from pathlib import Path
from pgdbm import AsyncMigrationManager
from .database import db

async def run_migrations():
    """Run all pending migrations"""
    migrations = AsyncMigrationManager(
        db,
        migrations_path=Path(__file__).parent / "migrations"
    )

    # Check pending
    pending = await migrations.get_pending_migrations()
    if not pending:
        print("No pending migrations")
        return

    print(f"Applying {len(pending)} migrations...")

    # Apply with progress
    for migration in pending:
        print(f"Applying {migration.filename}...", end="", flush=True)
        result = await migrations.apply_single(migration)
        print(f" done ({result.execution_time_ms}ms)")

if __name__ == "__main__":
    asyncio.run(run_migrations())
```

## Troubleshooting

### Migration Fails with "Permission Denied"

```
Error: permission denied to create extension "vector"
```

**Solution**: Extensions often require superuser privileges. Either:
1. Run as superuser: `CREATE EXTENSION IF NOT EXISTS vector;`
2. Have a DBA create the extension first
3. Grant necessary permissions to your application user

### Tables Created in Wrong Schema

**Symptom**: Tables appear in `public` instead of your assigned schema

**Causes and Solutions**:
1. **Missing {{tables.}} syntax**: Ensure ALL table references use `{{tables.tablename}}`
2. **Direct schema references**: Replace `public.users` with `{{tables.users}}`
3. **Missing schema in db manager**: Verify `AsyncDatabaseManager(schema="myschema")`

### Migration Already Applied Error

```
Error: Migration 001_initial.sql has been modified after being applied
```

**Cause**: The migration file was changed after deployment

**Solutions**:
1. **Never modify applied migrations** - Create new migrations for changes
2. **In development only**: Delete the migration record:
   ```sql
   DELETE FROM schema_migrations
   WHERE module_name = 'your_module' AND version = '001';
   ```

### Concurrent Migration Runs

**Symptom**: Multiple instances trying to apply same migration

**Solution**: pgdbm handles this automatically with database locks. The first instance applies the migration, others skip it.

### Schema Not Found

```
Error: schema "myapp" does not exist
```

**Solutions**:
1. Create schema before migrations:
   ```python
   await db.execute('CREATE SCHEMA IF NOT EXISTS "myapp"')
   ```
2. Grant schema permissions:
   ```sql
   GRANT CREATE, USAGE ON SCHEMA myapp TO app_user;
   ```

### Foreign Key References Fail

**Symptom**: `relation "users" does not exist` when creating foreign keys

**Solution**: Ensure correct migration order and use `{{tables.}}`:
```sql
-- Wrong: assumes public schema
user_id INTEGER REFERENCES users(id)

-- Correct: works with any schema
user_id INTEGER REFERENCES {{tables.users}}(id)
```

### Cross-Schema References

**Important**: PostgreSQL foreign keys cannot cross schemas. If you need to reference data in another schema, use application-level validation:

```python
# Can't do this in SQL:
# user_id INTEGER REFERENCES other_schema.users(id)

# Instead, validate in application:
async def create_order(self, user_id: UUID):
    # Validate user exists in users schema
    user = await user_service.get_user(user_id)
    if not user:
        raise ValueError("User not found")

    # Create order in orders schema
    return await self.db.fetch_one("""
        INSERT INTO {{tables.orders}} (user_id, ...)
        VALUES ($1, ...)
        RETURNING *
    """, user_id)
```

### Finding Which Migrations Ran

```python
# Check migration history
history = await db.fetch_all("""
    SELECT module_name, version, filename, applied_at
    FROM schema_migrations
    ORDER BY applied_at DESC
    LIMIT 10
""")
```

## Next Steps

- [Testing Guide](testing.md) - Test your migrations
- [Patterns Guide](patterns.md) - Deployment patterns for libraries and apps
