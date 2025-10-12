# Copyright (c) 2025 Juan Reyero
# Licensed under the MIT License

# ABOUTME: Public API for pgdbm library, exports core classes and functions for PostgreSQL database management.
# ABOUTME: Provides AsyncDatabaseManager, migrations, monitoring, testing utilities, and custom error classes.

"""
Async-first database utilities for PostgreSQL with connection pooling, migrations, and testing support.
"""

from pgdbm.__version__ import __author__, __author_email__, __license__, __version__
from pgdbm.core import AsyncDatabaseManager, DatabaseConfig, SchemaManager, TransactionManager
from pgdbm.errors import (
    AsyncDBError,
    ConfigurationError,
    ConnectionError,
    DatabaseTestError,
    MigrationError,
    MonitoringError,
    PoolError,
    QueryError,
    SchemaError,
    TransactionError,
)
from pgdbm.migrations import AsyncMigrationManager, Migration
from pgdbm.monitoring import (
    ConnectionMetrics,
    DatabaseDebugger,
    MonitoredAsyncDatabaseManager,
    QueryMetrics,
    log_query_performance,
)

# Import from testing.py file, not the testing/ directory
from pgdbm.testing import AsyncTestDatabase, DatabaseTestCase, DatabaseTestConfig

__all__ = [
    # Version info
    "__version__",
    "__author__",
    "__author_email__",
    "__license__",
    # Core
    "AsyncDatabaseManager",
    "DatabaseConfig",
    "SchemaManager",
    "TransactionManager",
    # Migrations
    "AsyncMigrationManager",
    "Migration",
    # Testing
    "AsyncTestDatabase",
    "DatabaseTestCase",
    "DatabaseTestConfig",
    # Monitoring
    "ConnectionMetrics",
    "DatabaseDebugger",
    "MonitoredAsyncDatabaseManager",
    "QueryMetrics",
    "log_query_performance",
    # Errors
    "AsyncDBError",
    "ConfigurationError",
    "ConnectionError",
    "MigrationError",
    "MonitoringError",
    "PoolError",
    "QueryError",
    "SchemaError",
    "DatabaseTestError",
    "TransactionError",
]

# Note: The testing.conftest module should be imported directly by users:
# from pgdbm.testing.conftest import *
