# Copyright (c) 2025 Juan Reyero
# Licensed under the MIT License

# ABOUTME: Custom exception classes for pgdbm with detailed error messages, context, and troubleshooting information.
# ABOUTME: Includes QueryError with parameter masking, ConnectionError, MigrationError, and other specific error types.

"""
Custom exceptions for pgdbm with helpful error messages and troubleshooting tips.
"""

from typing import Any, Optional


class AsyncDBError(Exception):
    """Base exception for all pgdbm errors."""

    def __init__(self, message: str, details: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.details = details or {}


class ConfigurationError(AsyncDBError):
    """Raised when there's an issue with database configuration."""

    def __init__(self, message: str, config_field: Optional[str] = None):
        self.config_field = config_field
        details = {"config_field": config_field} if config_field else {}
        super().__init__(message, details)


class ConnectionError(AsyncDBError):
    """Raised when database connection fails."""

    def __init__(
        self,
        message: str,
        host: Optional[str] = None,
        port: Optional[int] = None,
        database: Optional[str] = None,
        attempts: Optional[int] = None,
    ):
        details = {
            "host": host,
            "port": port,
            "database": database,
            "attempts": attempts,
        }
        full_message = f"{message}\n\nTroubleshooting tips:\n"
        full_message += "  - Check if PostgreSQL is running\n"
        full_message += f"  - Verify connection to {host}:{port}\n" if host and port else ""
        full_message += f"  - Ensure database '{database}' exists\n" if database else ""
        full_message += "  - Check firewall and network settings\n"
        full_message += "  - Verify credentials are correct"

        super().__init__(full_message, {k: v for k, v in details.items() if v is not None})


class PoolError(AsyncDBError):
    """Raised when there's an issue with connection pool management."""

    pass


class SchemaError(AsyncDBError):
    """Raised when there's an issue with schema operations."""

    def __init__(self, message: str, schema: Optional[str] = None):
        details = {"schema": schema} if schema else {}
        super().__init__(message, details)


class MigrationError(AsyncDBError):
    """Raised when database migration fails."""

    def __init__(
        self,
        message: str,
        migration_file: Optional[str] = None,
        version: Optional[str] = None,
        sql_error: Optional[str] = None,
    ):
        details = {
            "migration_file": migration_file,
            "version": version,
            "sql_error": sql_error,
        }
        full_message = f"{message}"
        if migration_file:
            full_message += f"\n  Migration file: {migration_file}"
        if version:
            full_message += f"\n  Version: {version}"
        if sql_error:
            full_message += f"\n  SQL Error: {sql_error}"

        super().__init__(full_message, {k: v for k, v in details.items() if v is not None})


class DatabaseTestError(AsyncDBError):
    """Raised when test database operations fail."""

    def __init__(self, message: str, test_db_name: Optional[str] = None):
        details = {"test_db_name": test_db_name} if test_db_name else {}
        super().__init__(message, details)


class QueryError(AsyncDBError):
    """Raised when a database query fails."""

    def __init__(
        self,
        message: str,
        query: Optional[str] = None,
        params: Optional[tuple] = None,
        original_error: Optional[Exception] = None,
    ):
        # Mask potentially sensitive parameters in error messages
        masked_params = self._mask_params(params) if params else None

        details = {
            "query": query,
            "params": masked_params,  # Store masked version
            "original_error": str(original_error) if original_error else None,
        }
        full_message = f"{message}"
        if query:
            # Truncate long queries
            display_query = query[:200] + "..." if len(query) > 200 else query
            full_message += f"\n  Query: {display_query}"
        if masked_params:
            full_message += f"\n  Parameters: {masked_params}"
        if original_error:
            full_message += f"\n  Original error: {original_error}"

        super().__init__(full_message, {k: v for k, v in details.items() if v is not None})

    @staticmethod
    def _mask_params(params: tuple) -> tuple:
        """Mask potentially sensitive parameters for error messages."""
        masked = []
        for param in params:
            if isinstance(param, str) and len(param) > 20:
                # Mask long strings that might contain passwords or sensitive data
                masked.append(f"<str:{len(param)} chars>")
            elif isinstance(param, bytes):
                # Mask binary data
                masked.append(f"<bytes:{len(param)} bytes>")
            else:
                # Keep short strings, numbers, booleans, None as-is
                masked.append(param)
        return tuple(masked)


class TransactionError(AsyncDBError):
    """Raised when a transaction operation fails."""

    pass


class MonitoringError(AsyncDBError):
    """Raised when monitoring operations fail."""

    pass
