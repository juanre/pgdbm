# API Reference

This document provides a complete reference for all public APIs in pgdbm.

## Table of Contents

- [Core Classes](#core-classes)
  - [DatabaseConfig](#databaseconfig)
  - [AsyncDatabaseManager](#asyncdatabasemanager)
  - [TransactionManager](#transactionmanager)
- [Migration Management](#migration-management)
  - [AsyncMigrationManager](#asyncmigrationmanager)
  - [Migration](#migration)
- [Monitoring](#monitoring)
  - [MonitoredAsyncDatabaseManager](#monitoredasyncdatabasemanager)
  - [DatabaseDebugger](#databasedebugger)
- [Testing Utilities](#testing-utilities)
  - [AsyncTestDatabase](#asynctestdatabase)
  - [DatabaseTestCase](#databasetestcase)
  - [DatabaseTestConfig](#databasetestconfig)
- [Error Classes](#error-classes)
- [Type Definitions](#type-definitions)

## Core Classes

### DatabaseConfig

Configuration for database connections.

```python
from pgdbm import DatabaseConfig

config = DatabaseConfig(
    host="localhost",
    port=5432,
    database="myapp",
    user="postgres",
    password="secret",
    schema="public"
)
```

#### Parameters

| Parameter                          | Type                       | Default       | Description                                                                  |
|------------------------------------|----------------------------|---------------|------------------------------------------------------------------------------|
| `connection_string`                | `Optional[str]`            | `None`        | Full PostgreSQL connection URL. If provided, overrides individual parameters |
| `host`                             | `str`                      | `"localhost"` | Database host                                                                |
| `port`                             | `int`                      | `5432`        | Database port                                                                |
| `database`                         | `str`                      | `"postgres"`  | Database name                                                                |
| `user`                             | `str`                      | `"postgres"`  | Database user                                                                |
| `password`                         | `Optional[str]`            | `None`        | Database password (required unless using DB_PASSWORD env var)                |
| `schema`                           | `Optional[str]`            | `None`        | Default schema name for multi-tenant applications                            |
| `min_connections`                  | `int`                      | `10`          | Minimum number of connections in pool                                        |
| `max_connections`                  | `int`                      | `20`          | Maximum number of connections in pool                                        |
| `max_queries`                      | `int`                      | `50000`       | Maximum queries per connection before recycling                              |
| `max_inactive_connection_lifetime` | `float`                    | `300.0`       | Seconds before closing idle connections                                      |
| `command_timeout`                  | `float`                    | `60.0`        | Default command timeout in seconds                                           |
| `server_settings`                  | `Optional[dict[str, str]]` | `None`        | PostgreSQL server settings                                                   |
| `init_commands`                    | `Optional[list[str]]`      | `None`        | SQL commands to run on each new connection                                   |
| `retry_attempts`                   | `int`                      | `3`           | Number of connection retry attempts                                          |
| `retry_delay`                      | `float`                    | `1.0`         | Initial delay between retries in seconds                                     |
| `retry_backoff`                    | `float`                    | `2.0`         | Backoff multiplier for exponential retry                                     |
| `retry_max_delay`                  | `float`                    | `30.0`        | Maximum delay between retries                                                |

#### Methods

##### get_dsn() -> str
Returns the PostgreSQL connection string. Handles password from environment variable `DB_PASSWORD` if not provided in config.

##### get_dsn_masked() -> str
Returns the connection string with password masked for logging.

##### get_schema() -> Optional[str]
Returns the configured schema name.

##### get_server_settings() -> dict[str, str]
Returns server settings including search path configuration.

### AsyncDatabaseManager

Main database manager for executing queries and managing connections.

```python
from pgdbm import AsyncDatabaseManager, DatabaseConfig

config = DatabaseConfig(host="localhost", database="myapp")
db = AsyncDatabaseManager(config)
await db.connect()
```

#### Constructor

```python
AsyncDatabaseManager(
    config: Optional[DatabaseConfig] = None,
    pool: Optional[asyncpg.Pool] = None,
    schema: Optional[str] = None
)
```

| Parameter | Type                       | Description                                               |
|-----------|----------------------------|-----------------------------------------------------------|
| `config`  | `Optional[DatabaseConfig]` | Database configuration (required if pool not provided)    |
| `pool`    | `Optional[asyncpg.Pool]`   | External connection pool (mutually exclusive with config) |
| `schema`  | `Optional[str]`            | Schema override (only valid with external pool)           |

#### Connection Management

##### async connect() -> None
Initialize the connection pool. Should be called once at application startup.

```python
await db.connect()
```

##### async disconnect() -> None
Close the connection pool. Should be called at application shutdown.

```python
await db.disconnect()
```

##### @classmethod async create_shared_pool(config: DatabaseConfig) -> asyncpg.Pool
Create a shared connection pool for use by multiple managers.

```python
pool = await AsyncDatabaseManager.create_shared_pool(config)
auth_db = AsyncDatabaseManager(pool=pool, schema="auth")
billing_db = AsyncDatabaseManager(pool=pool, schema="billing")
```

#### Query Execution

##### async execute(query: str, *args: Any, timeout: Optional[float] = None) -> str
Execute a query without returning results.

```python
await db.execute(
    "INSERT INTO users (email, name) VALUES ($1, $2)",
    "alice@example.com",
    "Alice Smith"
)
```

##### async executemany(query: str, args_list: list[tuple]) -> None
Execute a query with multiple parameter sets.

Compatibility alias: `execute_many(query, args_list)`

```python
await db.executemany(
    "INSERT INTO users (email, name) VALUES ($1, $2)",
    [
        ("alice@example.com", "Alice"),
        ("bob@example.com", "Bob"),
        ("charlie@example.com", "Charlie")
    ]
)
```

##### async fetch_one(query: str, *args: Any, timeout: Optional[float] = None) -> Optional[dict[str, Any]]
Fetch a single row as a dictionary.

```python
user = await db.fetch_one(
    "SELECT * FROM users WHERE email = $1",
    "alice@example.com"
)
if user:
    print(f"Found user: {user['name']}")
```

##### async fetch_all(query: str, *args: Any, timeout: Optional[float] = None) -> list[dict[str, Any]]
Fetch all rows as a list of dictionaries.

```python
users = await db.fetch_all(
    "SELECT * FROM users WHERE created_at > $1",
    datetime(2024, 1, 1)
)
for user in users:
    print(f"{user['email']}: {user['name']}")
```

##### async fetch_value(query: str, *args: Any, column: int = 0, timeout: Optional[float] = None) -> Any
Fetch a single value from the first row.

Compatibility alias: `fetch_val(query, *args, column=0, timeout=None)`

```python
count = await db.fetch_value("SELECT COUNT(*) FROM users")
print(f"Total users: {count}")

# Fetch specific column
email = await db.fetch_value(
    "SELECT email, name FROM users WHERE id = $1",
    user_id,
    column=0  # Returns email (0-indexed)
)
```

##### async execute_and_return_id(query: str, *args: Any) -> Any
Execute an INSERT and return the generated ID.

```python
user_id = await db.execute_and_return_id(
    "INSERT INTO users (email, name) VALUES ($1, $2)",
    "alice@example.com",
    "Alice"
)
# Automatically adds RETURNING id if not present
```

#### Transactions

##### @asynccontextmanager async transaction() -> AsyncIterator[TransactionManager]
Execute queries in a transaction context with automatic template substitution.

```python
async with db.transaction() as tx:
    user_id = await tx.fetch_value(
        "INSERT INTO {{tables.users}} (email) VALUES ($1) RETURNING id",
        "alice@example.com"
    )
    await tx.execute(
        "INSERT INTO {{tables.user_profiles}} (user_id, bio) VALUES ($1, $2)",
        user_id,
        "Software developer"
    )
    # Template substitution automatic, committed on success, rolled back on exception
```

##### @asynccontextmanager async acquire() -> AsyncIterator[Connection]
Acquire a connection from the pool.

```python
async with db.acquire() as conn:
    # Use connection for multiple operations
    await conn.execute("SET work_mem = '256MB'")
    result = await conn.fetch("SELECT * FROM large_table")
```

#### Schema and Tables

##### async table_exists(table_name: str) -> bool
Check if a table exists in the database.

```python
if await db.table_exists("users"):
    print("Users table exists")
```

#### Advanced Features

##### async copy_records_to_table(table_name: str, records: list[tuple], columns: Optional[list[str]] = None) -> int
Efficiently bulk insert records using PostgreSQL COPY. Pass the unqualified table
name (schema is applied automatically). Do not include a schema-qualified name; set
`schema` on the database manager instead. Ensure record tuples match the column order.

```python
records = [
    ("alice@example.com", "Alice"),
    ("bob@example.com", "Bob"),
    ("charlie@example.com", "Charlie")
]
rows_copied = await db.copy_records_to_table(
    "users",
    records,
    columns=["email", "name"]
)
print(f"Copied {rows_copied} rows")
```

##### async fetch_as_model(model: type[T], query: str, *args: Any) -> Optional[T]
Fetch a single row and convert to a Pydantic model.

```python
from pydantic import BaseModel

class User(BaseModel):
    id: int
    email: str
    name: str

user = await db.fetch_as_model(
    User,
    "SELECT * FROM users WHERE id = $1",
    user_id
)
```

##### async fetch_all_as_model(model: type[T], query: str, *args: Any) -> list[T]
Fetch all rows and convert to Pydantic models.

```python
users = await db.fetch_all_as_model(
    User,
    "SELECT * FROM users WHERE active = true"
)
```

##### add_prepared_statement(name: str, query: str) -> None
Register a prepared statement for improved performance.

```python
db.add_prepared_statement(
    "get_user_by_email",
    "SELECT * FROM users WHERE email = $1"
)
```

##### async get_pool_stats() -> dict[str, Any]
Get connection pool statistics for monitoring.

```python
stats = await db.get_pool_stats()
print(f"Pool size: {stats['size']}")
print(f"Free connections: {stats['free_size']}")
print(f"Used connections: {stats['used_size']}")
```

##### prepare_query(query: str) -> str
Prepare a query by applying template substitution for `{{tables.}}` and `{{schema}}` placeholders.

```python
# Manually prepare a query (rarely needed - transactions do this automatically)
prepared = db.prepare_query("SELECT * FROM {{tables.users}}")
# With schema="myapp": "SELECT * FROM \"myapp\".users"
```

### TransactionManager

Wrapper for database connections within transactions that automatically handles template substitution.

**Important**: You don't create TransactionManager instances directly. They are returned by `AsyncDatabaseManager.transaction()`.

```python
async with db.transaction() as tx:
    # tx is a TransactionManager instance
    await tx.execute("INSERT INTO {{tables.users}} (email) VALUES ($1)", email)
```

#### Methods

All methods automatically apply `{{tables.}}` and `{{schema}}` template substitution.

##### async execute(query: str, *args: Any, timeout: Optional[float] = None) -> str
Execute a query without returning results.

```python
async with db.transaction() as tx:
    await tx.execute(
        "INSERT INTO {{tables.users}} (email, name) VALUES ($1, $2)",
        "alice@example.com",
        "Alice"
    )
```

##### async executemany(query: str, args_list: list[tuple]) -> None
Execute a query with multiple parameter sets.

Compatibility alias: `execute_many(query, args_list)`

```python
async with db.transaction() as tx:
    await tx.executemany(
        "INSERT INTO {{tables.users}} (email, name) VALUES ($1, $2)",
        [
            ("alice@example.com", "Alice"),
            ("bob@example.com", "Bob"),
        ],
    )
```

##### async fetch_one(query: str, *args: Any, timeout: Optional[float] = None) -> Optional[dict[str, Any]]
Fetch a single row as a dictionary.

```python
async with db.transaction() as tx:
    user = await tx.fetch_one(
        "SELECT * FROM {{tables.users}} WHERE email = $1",
        "alice@example.com"
    )
    if user:
        print(f"Found: {user['name']}")
```

##### async fetch_all(query: str, *args: Any, timeout: Optional[float] = None) -> list[dict[str, Any]]
Fetch all rows as a list of dictionaries.

```python
async with db.transaction() as tx:
    users = await tx.fetch_all(
        "SELECT * FROM {{tables.users}} WHERE active = true"
    )
    for user in users:
        print(user['email'])
```

##### async fetch_value(query: str, *args: Any, column: int = 0, timeout: Optional[float] = None) -> Any
Fetch a single value from the first row.

Compatibility alias: `fetch_val(query, *args, column=0, timeout=None)`

```python
async with db.transaction() as tx:
    count = await tx.fetch_value(
        "SELECT COUNT(*) FROM {{tables.users}}"
    )
    print(f"Total users: {count}")
```

#### Usage Notes

1. **Template Substitution**: All queries are automatically processed for `{{tables.}}` and `{{schema}}` placeholders
2. **Consistent API**: Same method names and return types as `AsyncDatabaseManager`
3. **Automatic Commit/Rollback**: Transaction commits on success, rolls back on exception
4. **Nested Transactions**: Use `tx.transaction()` for savepoints

```python
async with db.transaction() as tx:
    # Outer transaction
    await tx.execute("INSERT INTO {{tables.orders}} (...) VALUES (...)")

    # Nested transaction (savepoint)
    async with tx.transaction():
        await tx.execute("INSERT INTO {{tables.order_items}} (...) VALUES (...)")
        # If this fails, only the nested transaction rolls back
```

5. **Advanced**: For raw connection access, use `tx.connection` property (rarely needed)

## Migration Management

### AsyncMigrationManager

Manages database migrations with checksum verification and module support.

```python
from pgdbm import AsyncMigrationManager

migrations = AsyncMigrationManager(
    db_manager=db,
    migrations_path="./migrations",
    migrations_table="schema_migrations",
    module_name="myapp"
)
```

#### Constructor Parameters

| Parameter          | Type                   | Default               | Description                          |
|--------------------|------------------------|-----------------------|--------------------------------------|
| `db_manager`       | `AsyncDatabaseManager` | Required              | Database manager instance            |
| `migrations_path`  | `str`                  | `"./migrations"`      | Path to migration files              |
| `migrations_table` | `str`                  | `"schema_migrations"` | Table name for tracking migrations   |
| `module_name`      | `Optional[str]`        | Schema or `"default"` | Module name for multi-module support |

#### Methods

##### async ensure_migrations_table() -> None
Create the migrations tracking table if it doesn't exist.

##### async get_applied_migrations() -> dict[str, Migration]
Get dictionary of applied migrations keyed by filename.

##### async get_pending_migrations() -> list[Migration]
Get list of migrations that haven't been applied yet.

##### async apply_pending_migrations(dry_run: bool = False) -> dict[str, Any]
Apply all pending migrations.

```python
result = await migrations.apply_pending_migrations()
print(f"Applied {len(result['applied'])} migrations")
for migration in result['applied']:
    print(f"  - {migration['filename']} ({migration['execution_time_ms']}ms)")
```

Return dictionary contains:
- `status`: "success", "error", "up_to_date", or "dry_run"
- `applied`: List of applied migrations
- `skipped`: List of already applied migrations
- `total`: Total number of migrations
- `error`: Error message (if status is "error")
- `failed_migration`: Filename of failed migration (if status is "error")

##### async apply_migration(migration: Migration) -> float
Apply a single migration and return execution time in milliseconds.

##### async find_migration_files() -> list[Migration]
Find all SQL files in the migrations directory.

##### async create_migration(name: str, content: str, auto_transaction: bool = True) -> str
Create a new migration file with timestamp prefix.

```python
filepath = await migrations.create_migration(
    name="add_user_roles",
    content="""
        CREATE TABLE user_roles (
            user_id INTEGER REFERENCES users(id),
            role VARCHAR(50) NOT NULL
        );
    """,
    auto_transaction=True  # Wraps in BEGIN/COMMIT
)
```

##### async rollback_migration(filename: str) -> None
Remove a migration record (does not undo schema changes).

##### async get_migration_history(limit: int = 10) -> list[dict[str, Any]]
Get recent migration history with execution details.

### Migration

Represents a database migration file.

```python
class Migration(BaseModel):
    filename: str
    checksum: str
    content: str
    applied_at: Optional[datetime] = None
    module_name: Optional[str] = None
```

#### Properties

##### is_applied -> bool
Check if migration has been applied.

##### version -> str
Extract version from filename. Supports:
- Numeric prefix: `001_create_users.sql` → "001"
- Flyway style: `V1__create_users.sql` → "1"
- Timestamp: `20240126120000_users.sql` → "20240126120000"

## Monitoring

### MonitoredAsyncDatabaseManager

Extended database manager with built-in monitoring and metrics.

```python
from pgdbm import MonitoredAsyncDatabaseManager

monitored_db = MonitoredAsyncDatabaseManager(
    config=config,
    slow_query_threshold_ms=1000,  # Log queries slower than 1000ms
    max_history_size=1000
)
```

#### Additional Constructor Parameters

| Parameter                  | Type   | Default | Description                                      |
|----------------------------|--------|---------|--------------------------------------------------|
| `slow_query_threshold_ms`  | `int`  | `1000`  | Threshold in milliseconds for slow query logging |
| `max_history_size`         | `int`  | `1000`  | Number of queries to keep in history             |
| `record_args`              | `bool` | `False` | Record masked query arguments in history         |

#### Additional Methods

##### async get_metrics() -> ConnectionMetrics
Get aggregated query performance and connection metrics.

```python
metrics = await monitored_db.get_metrics()
print(f"Total queries: {metrics.queries_executed}")
print(f"Average duration: {metrics.avg_query_time_ms}ms")
print(f"Pool utilization: {metrics.pool_utilization}%")
```

Returns a `ConnectionMetrics` object with properties:
- `queries_executed`: Total queries executed
- `queries_failed`: Total failed queries
- `avg_query_time_ms`: Average query time in milliseconds
- `slowest_query_ms`: Slowest query time
- `pool_size`, `pool_free`, `pool_used`: Connection pool statistics
- `pool_utilization`: Pool usage percentage (0-100)

##### get_slow_queries(threshold_ms: Optional[float] = None) -> list[QueryMetrics]
Get queries that exceeded the threshold.

```python
# Use configured threshold
slow_queries = monitored_db.get_slow_queries()

# Or specify custom threshold
very_slow = monitored_db.get_slow_queries(threshold_ms=5000)

for query in slow_queries:
    print(f"{query.duration_ms}ms: {query.query[:50]}...")
```

##### get_query_history(limit: Optional[int] = None, include_errors: bool = True) -> list[QueryMetrics]
Get recent query execution history.

By default, query arguments are not stored; pass `record_args=True` to record masked arguments.

```python
# Get last 20 queries
history = monitored_db.get_query_history(limit=20)

# Get only successful queries
successful = monitored_db.get_query_history(include_errors=False)

for query in history:
    print(f"{query.duration_ms}ms: {query.query[:50]}")
```

##### async explain_query(query: str, *args: Any, analyze: bool = False) -> list[dict[str, Any]]
Get query execution plan using EXPLAIN.

```python
# Get execution plan
plan = await monitored_db.explain_query(
    "SELECT * FROM {{tables.users}} WHERE active = true"
)

# Get actual execution stats with EXPLAIN ANALYZE
analyzed = await monitored_db.explain_query(
    "SELECT * FROM {{tables.orders}} WHERE user_id = $1",
    user_id,
    analyze=True
)
```

### DatabaseDebugger

Utilities for debugging database performance and issues.

```python
from pgdbm import DatabaseDebugger

debugger = DatabaseDebugger(db_manager)
```

#### Methods

##### async check_connection_health() -> dict[str, Any]
Comprehensive health check of database connections. Returns status, connectivity info, pool stats, blocking queries, and long-running queries.

```python
health = await debugger.check_connection_health()
print(f"Status: {health['status']}")  # 'healthy', 'degraded', or 'unhealthy'
print(f"Connectivity: {health['checks']['connectivity']['status']}")
print(f"Blocking queries: {health['checks']['blocking_queries']['count']}")
print(f"Long-running queries: {health['checks']['long_running_queries']['count']}")
```

##### async find_blocking_queries() -> list[dict[str, Any]]
Find queries that are blocking other queries.

```python
blocking = await debugger.find_blocking_queries()
for query in blocking:
    print(f"PID {query['blocking_pid']} is blocking PID {query['blocked_pid']}")
    print(f"Blocking query: {query['blocking_query']}")
```

##### async find_long_running_queries(threshold_seconds: int = 300) -> list[dict[str, Any]]
Find queries running longer than threshold.

```python
long_queries = await debugger.find_long_running_queries(threshold_seconds=60)
for query in long_queries:
    print(f"Query running for {query['duration']}: {query['query']}")
```

##### async analyze_table_sizes() -> list[dict[str, Any]]
Get table sizes and statistics.

```python
tables = await debugger.analyze_table_sizes()
for table in tables:
    print(f"{table['tablename']}: {table['size']} ({table['row_count']} rows)")
```

## Testing Utilities

### AsyncTestDatabase

Test database management for async tests with debugging support.

```python
from pgdbm import AsyncTestDatabase, DatabaseTestConfig

config = DatabaseTestConfig(
    host="localhost",
    port=5432,
    user="postgres",
    password="postgres",
    verbose=True,
    log_sql=True
)

test_db = AsyncTestDatabase(config)
```

#### Constructor Parameters

| Parameter | Type                           | Default               | Description                                  |
|-----------|--------------------------------|-----------------------|----------------------------------------------|
| `config`  | `Optional[DatabaseTestConfig]` | `from_env()` if None  | Test database configuration                  |

#### Methods

##### async create_test_database(suffix: Optional[str] = None) -> None
Create a new test database with optional suffix.

```python
await test_db.create_test_database("integration")
# Creates database like: test_myapp_integration_abc123
```

##### async drop_test_database() -> None
Drop the test database if it exists.

##### async get_test_db_config(schema: Optional[str] = None, **kwargs) -> DatabaseConfig
Get configuration for connecting to the test database.

##### async get_test_db_manager(schema: Optional[str] = None, **kwargs) -> AsyncDatabaseManager
Get a database manager connected to the test database.

```python
async with test_db.get_test_db_manager() as db_manager:
    await db_manager.execute("CREATE TABLE users (...)")
    # Manager automatically connects and disconnects
```

##### async create(schema: Optional[str] = None, config: Optional[DatabaseTestConfig] = None, suffix: Optional[str] = None, **kwargs) -> AsyncGenerator[AsyncDatabaseManager, None]
Create a temporary test database and yield a connected manager.

```python
async with AsyncTestDatabase.create(schema="test") as db_manager:
    await db_manager.execute("CREATE TABLE users (...)")
```

##### async snapshot_table(db_manager: AsyncDatabaseManager, table_name: str, order_by: Optional[str] = None) -> list[dict[str, Any]]
Capture current state of a table for comparison.

```python
before = await test_db.snapshot_table(db_manager, "users")
# Perform operations
after = await test_db.snapshot_table(db_manager, "users")
assert before != after
```

### DatabaseTestCase

Utility class providing test helper methods.

```python
from pgdbm import DatabaseTestCase

test_utils = DatabaseTestCase(db_manager)
```

#### Methods

##### async create_test_user(email: str, **kwargs) -> dict[str, Any]
Create a test user with sensible defaults.

```python
user = await test_utils.create_test_user(
    "alice@example.com",
    name="Alice Smith",
    is_active=True
)
```

##### async count_rows(table_name: str, where: Optional[str] = None) -> int
Count rows in a table with optional WHERE clause.

```python
active_users = await test_utils.count_rows("users", "is_active = true")
```

##### async table_exists(table_name: str) -> bool
Check if a table exists.

##### async truncate_table(table_name: str, cascade: bool = False) -> None
Truncate a table.

### DatabaseTestConfig

Configuration for test databases.

```python
from pgdbm import DatabaseTestConfig

config = DatabaseTestConfig(
    host="localhost",
    port=5432,
    user="postgres",
    password="postgres",
    test_prefix="test_",
    verbose=True,
    log_sql=False
)
```

#### Parameters

| Parameter     | Type    | Default      | Description                      |
|---------------|---------|--------------|----------------------------------|
| `host`        | `str`   | `localhost`  | Database host                    |
| `port`        | `int`   | `5432`       | Database port                    |
| `user`        | `str`   | `postgres`   | Database user                    |
| `password`    | `str`   | `postgres`   | Database password                |
| `test_prefix` | `str`   | `test_`      | Prefix for test database names   |
| `verbose`     | `bool`  | `False`      | Enable verbose logging           |
| `log_sql`     | `bool`  | `False`      | Log SQL queries                  |

#### Class Methods

##### from_env() -> DatabaseTestConfig
Create configuration from environment variables:
- `TEST_DB_HOST`
- `TEST_DB_PORT`
- `TEST_DB_USER`
- `TEST_DB_PASSWORD`
- `TEST_DB_VERBOSE`
- `TEST_DB_LOG_SQL`

## Error Classes

pgdbm provides detailed error classes with context:

### Base Error

```python
class AsyncDBError(Exception):
    """Base exception for all pgdbm errors."""
    pass
```

### Configuration Errors

```python
class ConfigurationError(AsyncDBError):
    """Raised for configuration-related errors."""

    def __init__(self, message: str, config_field: Optional[str] = None):
        self.config_field = config_field
```

### Connection Errors

```python
class ConnectionError(AsyncDBError):
    """Raised when database connection fails."""

    def __init__(
        self,
        message: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        attempts: Optional[int] = None
    ):
        self.host = host
        self.port = port
        self.database = database
        self.attempts = attempts
```

### Pool Errors

```python
class PoolError(AsyncDBError):
    """Raised for connection pool errors."""
    pass
```

### Query Errors

```python
class QueryError(AsyncDBError):
    """Raised when query execution fails."""

    def __init__(
        self,
        message: str,
        query: Optional[str] = None,
        params: Optional[tuple] = None,
        original_error: Optional[Exception] = None
    ):
        self.query = query
        self.params = params
        self.original_error = original_error
```

QueryError automatically masks potentially sensitive parameters in error messages:
- Long strings (over 20 characters) are masked as `<str:N chars>` to protect passwords and sensitive data
- Binary data is masked as `<bytes:N bytes>`
- Short strings, numbers, booleans, and None values are included as-is

This prevents accidental exposure of sensitive information in logs and error messages while maintaining useful debugging context.

### Schema Errors

```python
class SchemaError(AsyncDBError):
    """Raised for schema-related errors."""

    def __init__(self, message: str, schema: Optional[str] = None):
        self.schema = schema
```

### Migration Errors

```python
class MigrationError(AsyncDBError):
    """Raised for migration-related errors."""

    def __init__(self, message: str, migration_file: Optional[str] = None):
        self.migration_file = migration_file
```

### Test Database Errors

```python
class DatabaseTestError(AsyncDBError):
    """Raised for test database errors."""

    def __init__(self, message: str, test_db_name: Optional[str] = None):
        self.test_db_name = test_db_name
```

### Transaction Errors

```python
class TransactionError(AsyncDBError):
    """Raised for transaction-related errors."""
    pass
```

### Monitoring Errors

```python
class MonitoringError(AsyncDBError):
    """Raised for monitoring-related errors."""
    pass
```

## Type Definitions

pgdbm is fully typed. Key type aliases:

```python
from typing import TypeVar, Union
from pydantic import BaseModel
import asyncpg

# Generic type for Pydantic models
T = TypeVar("T", bound=BaseModel)

# Connection type (either direct or from pool)
Connection = Union[asyncpg.Connection, asyncpg.pool.PoolConnectionProxy]
```

## Query Placeholders

pgdbm supports special placeholders for schema-aware queries:

- `{{schema}}` - Replaced with the quoted schema name (or "public" if no schema)
- `{{tables.tablename}}` - Replaced with schema-qualified table name

Examples:
```python
# With schema="myapp"
await db.execute("CREATE TABLE {{tables.users}} (...)")
# Executes: CREATE TABLE "myapp".users (...)

await db.execute("CREATE TYPE {{schema}}.status_enum AS ENUM ('active', 'inactive')")
# Executes: CREATE TYPE "myapp".status_enum AS ENUM ('active', 'inactive')

await db.execute("SELECT * FROM {{tables.users}} WHERE active = true")
# Executes: SELECT * FROM "myapp".users WHERE active = true

# Without schema (schema=None)
await db.execute("CREATE TABLE {{tables.users}} (...)")
# Executes: CREATE TABLE users (...)

await db.execute("CREATE TYPE {{schema}}.status_enum AS ENUM ('active', 'inactive')")
# Executes: CREATE TYPE public.status_enum AS ENUM ('active', 'inactive')
```

Use `{{schema}}` for PostgreSQL objects that need explicit schema:
- Functions and procedures
- Types (ENUM, composite types)
- Views
- Extensions

Use `{{tables.tablename}}` for table operations:
- CREATE/ALTER/DROP TABLE
- Foreign key references
- Indexes
- All DML queries (SELECT, INSERT, UPDATE, DELETE)

## Environment Variables

pgdbm supports these environment variables:

- `DB_PASSWORD` - Database password (used if not provided in config)
- `DB_DEBUG` - Set to "1", "true", or "yes" to enable debug logging
- `MIGRATION_DEBUG` - Set to "1", "true", or "yes" to enable migration debug logging
- `TEST_DB_HOST` - Test database host (default: localhost)
- `TEST_DB_PORT` - Test database port (default: 5432)
- `TEST_DB_USER` - Test database user (default: postgres)
- `TEST_DB_PASSWORD` - Test database password (default: postgres)
- `TEST_DB_VERBOSE` - Enable verbose test output
- `TEST_DB_LOG_SQL` - Log SQL queries in tests

## Thread Safety

pgdbm is designed for async/await usage and is not thread-safe. Use separate instances per thread or stick to asyncio for concurrent operations.

## Testing Best Practices

### Using Test Fixtures

Import pgdbm's ready-to-use pytest fixtures:

```python
# In your conftest.py
from pgdbm.fixtures.conftest import (
    test_db,
    test_db_with_schema,
    test_db_factory,
    test_db_with_tables,
    test_db_with_data,
    db_test_utils,
    test_db_isolated
)

# Or simply
from pgdbm.fixtures.conftest import *
```

### Test Isolation

1. **Separate Databases**: Each test gets a fresh database
2. **Schema Isolation**: Use `test_db_with_schema` for multi-tenant tests
3. **Transaction Rollback**: Use `test_db_isolated` to rollback after each test
4. **Factory Pattern**: Use `test_db_factory` for multiple databases in one test

## Connection Pooling Best Practices

1. **Pool Sizing**: Start with min=10, max=20 and adjust based on load
2. **Connection Lifetime**: Set `max_inactive_connection_lifetime` to prevent stale connections
3. **Query Recycling**: Use `max_queries` to periodically refresh connections
4. **Monitoring**: Use `get_pool_stats()` to track pool health
5. **Shared Pools**: Use `create_shared_pool()` when multiple components share a database

## Performance Tips

1. **Prepared Statements**: Use `add_prepared_statement()` for frequently executed queries
2. **Bulk Operations**: Use `copy_records_to_table()` for large inserts
3. **Connection Reuse**: Use transactions or `acquire()` for multiple related queries
4. **Indexing**: Monitor slow queries and add appropriate indexes
5. **Schema Placeholders**: Parsed once per query, minimal overhead

---
