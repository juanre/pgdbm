# Changelog

All notable changes to pgdbm will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.4.0] - 2026-01-17

### Added
- **Explicit schema syntax for cross-schema queries** via `{{tables.schema.tablename}}`
  - Enables queries across different schemas while maintaining backward compatibility
  - Works with or without a schema configured on the database manager
  - Schema and table names are validated to prevent SQL injection
- Table name validation in template placeholders for enhanced security
- `EXPLICIT_TABLE_PATTERN` and `IMPLICIT_TABLE_PATTERN` compiled regex constants

### Changed
- Refactored `prepare_query()` to use compiled regex patterns for better performance

## [0.3.0] - 2026-01-11

### Added
- **No-transaction migration mode** for DDL that cannot run inside a transaction block
  - Use magic comment `-- pgdbm:no-transaction` at the start of a line in migration files
  - Supports `CREATE INDEX CONCURRENTLY`, `DROP INDEX CONCURRENTLY`, `REINDEX CONCURRENTLY`
  - Migrations are split into individual statements and executed in autocommit mode
  - SQL-aware statement splitter handles quoted strings, dollar quotes, and comments
  - Warning log emitted to alert operators about partial commit risk
- `_split_sql_statements()` helper for SQL-aware statement splitting

### Fixed
- Magic comment detection uses anchored regex to prevent false positives
  - Now requires `-- pgdbm:no-transaction` at start of line followed by whitespace or end-of-line
  - Won't match variations like `-- pgdbm:no-transactional` or embedded mentions

### Documentation
- Documented idempotent statement requirement for no-transaction migrations
- Added warning about partial commit behavior when using no-transaction mode

## [0.2.1] - 2026-01-06

### Added
- `AsyncTestDatabase.create()` class method - context manager that creates a temporary test database and guarantees cleanup even if tests fail

### Fixed
- Test fixture cleanup hardened with `try/finally` blocks to prevent orphaned databases when tests fail
- All test fixtures (`test_db`, `test_db_with_schema`, `test_db_factory`) now properly clean up databases even on test exceptions

### Documentation
- Pool sizing recommendations clarified (start with 5/20, tune based on metrics)
- Clarified that pgdbm uses template substitution for schema isolation, not `search_path`
- Added database cleanup section to testing documentation

## [0.2.0] - 2026-01-05

### Added
- `TransactionManager` wrapper class for transactions with automatic template substitution
  - Returned by `AsyncDatabaseManager.transaction()` context manager
  - Automatically processes `{{tables.}}` and `{{schema}}` placeholders in all queries
  - Consistent API: `fetch_one()`, `fetch_all()`, `fetch_value()` return dictionaries
  - Maintains same method signatures as `AsyncDatabaseManager` for familiarity
- Public `prepare_query()` method on `AsyncDatabaseManager` for manual query preparation
  - Previously private `_prepare_query()` kept as backward compatibility alias
- TLS/SSL support in `DatabaseConfig` with `ssl_enabled`, `ssl_mode`, CA/cert/key options
- Server-side timeouts in `DatabaseConfig` (`statement_timeout_ms`, `idle_in_transaction_session_timeout_ms`, `lock_timeout_ms`)
- Advisory locking in migrations to serialize runners per `module_name`
- Migration version extraction from filenames
  - Supports numeric prefix (001_), Flyway style (V1__), and timestamp patterns
  - Automatic version property on Migration model
  - Better ordering and conflict prevention
- `fetch_val()` and `execute_many()` compatibility aliases

### Changed
- **BREAKING**: `AsyncDatabaseManager.transaction()` now returns `TransactionManager` instead of raw `asyncpg.Connection`
  - Old code using `conn.fetchrow()`, `conn.fetch()`, `conn.fetchval()` must update to `tx.fetch_one()`, `tx.fetch_all()`, `tx.fetch_value()`
  - Template substitution now automatic - no need to call `_prepare_query()` manually
  - See migration guide in documentation for upgrade instructions
- Replace generic exceptions with custom error types throughout codebase
  - ConfigurationError, PoolError, QueryError, MigrationError, etc.
  - Enhanced error messages with troubleshooting tips
  - Better debugging experience
- `execute_and_return_id` now correctly detects existing RETURNING clauses to avoid duplication
- **BREAKING**: Minimum Python version raised to 3.9
  - Python 3.8 reached EOL in October 2024
  - Allows use of modern type annotations and features

### Fixed
- Transaction template substitution now works correctly - `{{tables.}}` syntax applies automatically within transactions
- Example code in microservices (inventory and orders services) fixed to properly use transactions
- Migrations now use `TransactionManager` internally for consistent template handling
- Schema name validation at configuration time prevents SQL injection
- `copy_records_to_table` now correctly honors schema setting
- CLI `migrate apply` works without config file
- CLI works when event loop is already running
- Sensitive data no longer retained in query monitoring history
- Documentation aligned with actual API

### Security
- Schema identifiers validated against PostgreSQL naming rules before SQL use
- Monitoring `schema_filter` SQL injection vulnerability fixed
- Query arguments masked in error messages to prevent credential exposure

## [0.1.0] - 2025-01-26

### Added
- Initial public release
- Core async database management with connection pooling
- Schema-based multi-tenancy support
- Built-in migration system
- Comprehensive testing utilities
- Connection monitoring and debugging tools
- Shared connection pool support for microservices
- Full type hints and py.typed support
- Pytest fixtures for easy testing
- Production-ready patterns out of the box

### Features
- **AsyncDatabaseManager**: Main database interface with connection pooling
- **DatabaseConfig**: Pydantic-based configuration management
- **AsyncMigrationManager**: Database migration tracking and execution
- **MonitoredAsyncDatabaseManager**: Performance monitoring capabilities
- **Testing utilities**: Automatic test database creation and cleanup
- **Schema isolation**: Multi-tenant support with `{{tables.name}}` templating

[Unreleased]: https://github.com/juanre/pgdbm/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/juanre/pgdbm/compare/v0.2.0...v0.2.1
[0.2.0]: https://github.com/juanre/pgdbm/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/juanre/pgdbm/releases/tag/v0.1.0
