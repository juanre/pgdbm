# Changelog

All notable changes to pgdbm will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- TLS/SSL support in `DatabaseConfig` with `ssl_enabled`, `ssl_mode`, CA/cert/key options
- Server-side timeouts in `DatabaseConfig` (`statement_timeout_ms`, `idle_in_transaction_session_timeout_ms`, `lock_timeout_ms`)
- Advisory locking in migrations to serialize runners per `module_name`
- Migration version extraction from filenames
  - Supports numeric prefix (001_), Flyway style (V1__), and timestamp patterns
  - Automatic version property on Migration model
  - Better ordering and conflict prevention

### Changed
- Replace generic exceptions with custom error types throughout codebase
  - ConfigurationError, PoolError, QueryError, MigrationError, etc.
  - Enhanced error messages with troubleshooting tips
  - Better debugging experience
- `execute_and_return_id` now correctly detects existing RETURNING clauses to avoid duplication
- **BREAKING**: Minimum Python version raised to 3.9
  - Python 3.8 reached EOL in October 2024
  - Allows use of modern type annotations and features

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

[Unreleased]: https://github.com/juanreyero/pgdbm/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/juanreyero/pgdbm/releases/tag/v0.1.0
