# Copyright (c) 2025 Juan Reyero
# Licensed under the MIT License

"""
Core async database utilities for connection management, schema handling, and transaction control.
"""

import asyncio
import logging
import os
import re
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Optional, TypeVar, Union, cast

import asyncpg
from pydantic import BaseModel, ConfigDict, Field

from pgdbm.errors import ConfigurationError, ConnectionError, PoolError, QueryError, SchemaError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class DatabaseConfig(BaseModel):
    """Configuration for async database connections."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Connection parameters
    connection_string: Optional[str] = None
    host: str = "localhost"
    port: int = 5432
    database: str = "postgres"
    user: str = "postgres"
    password: Optional[str] = Field(
        default=None, description="Database password (required unless using DB_PASSWORD env var)"
    )
    schema_name: Optional[str] = Field(None, alias="schema")

    # Pool configuration
    min_connections: int = Field(default=10, description="Minimum number of connections in pool")
    max_connections: int = Field(default=20, description="Maximum number of connections in pool")
    max_queries: int = Field(
        default=50000, description="Maximum queries per connection before recycling"
    )
    max_inactive_connection_lifetime: float = Field(
        default=300.0, description="Seconds before closing idle connections"
    )
    command_timeout: float = Field(default=60.0, description="Default command timeout in seconds")

    # Connection initialization
    server_settings: Optional[dict[str, str]] = None
    init_commands: Optional[list[str]] = None

    # TLS/SSL configuration
    ssl_enabled: bool = Field(default=False, description="Enable TLS/SSL for database connections")
    ssl_mode: Optional[str] = Field(
        default=None,
        description=(
            "SSL mode: one of 'require', 'verify-ca', 'verify-full'. "
            "If None and ssl_enabled=True, defaults to 'verify-full'."
        ),
    )
    ssl_ca_file: Optional[str] = Field(default=None, description="Path to CA certificate file")
    ssl_cert_file: Optional[str] = Field(
        default=None, description="Path to client certificate file"
    )
    ssl_key_file: Optional[str] = Field(default=None, description="Path to client private key file")
    ssl_key_password: Optional[str] = Field(
        default=None, description="Password for encrypted private key"
    )

    # Server-side timeout safeguards (in milliseconds). Set to None to disable.
    statement_timeout_ms: Optional[int] = Field(
        default=60000,
        description="Abort any statement running longer than this duration (ms)",
    )
    idle_in_transaction_session_timeout_ms: Optional[int] = Field(
        default=60000,
        description="Abort sessions that remain idle in transaction longer than this duration (ms)",
    )
    lock_timeout_ms: Optional[int] = Field(
        default=5000,
        description="Abort attempts to acquire a lock after this duration (ms)",
    )

    # Retry configuration
    retry_attempts: int = Field(default=3, description="Number of connection retry attempts")
    retry_delay: float = Field(default=1.0, description="Initial delay between retries in seconds")
    retry_backoff: float = Field(
        default=2.0, description="Backoff multiplier for exponential retry"
    )
    retry_max_delay: float = Field(default=30.0, description="Maximum delay between retries")

    def get_dsn(self) -> str:
        """Get the database connection string (DSN)."""
        if self.connection_string:
            return self.connection_string

        # Support password from environment variable for security
        password = self.password
        if not password:
            password = os.environ.get("DB_PASSWORD", "")

        if not password:
            raise ConfigurationError(
                "Database password not provided. Set it in config or DB_PASSWORD environment variable.",
                config_field="password",
            )

        # URL encode password to handle special characters
        from urllib.parse import quote_plus

        encoded_password = quote_plus(password)

        return (
            f"postgresql://{self.user}:{encoded_password}@"
            f"{self.host}:{self.port}/{self.database}"
        )

    def get_dsn_masked(self) -> str:
        """Get the database connection string with password masked for logging."""
        if self.connection_string:
            # Mask password in connection string
            return re.sub(r"://([^:]+):([^@]+)@", r"://\1:****@", self.connection_string)

        return f"postgresql://{self.user}:****@" f"{self.host}:{self.port}/{self.database}"

    def get_schema(self) -> Optional[str]:
        """Get the schema name."""
        return self.schema_name

    def get_server_settings(self) -> dict[str, str]:
        """Get server settings including search path."""
        settings = self.server_settings or {}
        if self.schema_name:
            settings["search_path"] = f'"{self.schema_name}", public'
        settings.setdefault("jit", "off")  # JIT can cause latency spikes
        settings.setdefault("application_name", f'{self.schema_name or "app"}_pool')
        # Apply default timeouts if not explicitly set by caller
        if self.statement_timeout_ms is not None:
            settings.setdefault("statement_timeout", str(int(self.statement_timeout_ms)))
        if self.idle_in_transaction_session_timeout_ms is not None:
            settings.setdefault(
                "idle_in_transaction_session_timeout",
                str(int(self.idle_in_transaction_session_timeout_ms)),
            )
        if self.lock_timeout_ms is not None:
            settings.setdefault("lock_timeout", str(int(self.lock_timeout_ms)))
        return settings

    def build_ssl_context(self) -> Optional[ssl.SSLContext]:
        """Build an SSL context based on configuration or return None if disabled.

        Modes:
          - require: encrypt traffic, do not verify server cert
          - verify-ca: verify server cert against CA, do not verify hostname
          - verify-full: verify server cert and hostname
        """
        if not self.ssl_enabled:
            return None

        mode = (self.ssl_mode or "verify-full").lower()
        if mode not in {"require", "verify-ca", "verify-full"}:
            raise ConfigurationError(
                "Invalid ssl_mode. Expected one of: 'require', 'verify-ca', 'verify-full'",
                config_field="ssl_mode",
            )

        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

        if mode == "require":
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        elif mode == "verify-ca":
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_REQUIRED
        else:  # verify-full
            ctx.check_hostname = True
            ctx.verify_mode = ssl.CERT_REQUIRED

        # Load CA bundle if provided
        if self.ssl_ca_file:
            try:
                ctx.load_verify_locations(cafile=self.ssl_ca_file)
            except Exception as e:
                raise ConfigurationError(
                    f"Failed to load CA file: {e}", config_field="ssl_ca_file"
                ) from e

        # Load client cert/key if provided (mutual TLS)
        if self.ssl_cert_file and self.ssl_key_file:
            try:
                ctx.load_cert_chain(
                    certfile=self.ssl_cert_file,
                    keyfile=self.ssl_key_file,
                    password=self.ssl_key_password,
                )
            except Exception as e:
                raise ConfigurationError(
                    f"Failed to load client certificate/key: {e}", config_field="ssl_cert_file"
                ) from e

        return ctx


class AsyncDatabaseManager:
    """Async database manager with connection pooling and debugging support."""

    def __init__(
        self,
        config: Optional[DatabaseConfig] = None,
        pool: Optional[asyncpg.Pool] = None,
        schema: Optional[str] = None,
    ):
        """
        Initialize database manager.

        Args:
            config: Database configuration (required if pool not provided)
            pool: External connection pool to use (mutually exclusive with config)
            schema: Override schema name (only valid with external pool)
        """
        if pool and config:
            raise ConfigurationError(
                "Cannot provide both config and pool parameters. "
                "Use either a DatabaseConfig OR an external pool, not both."
            )
        if not pool and not config:
            raise ConfigurationError(
                "Must provide either config or pool parameter. "
                "Initialize with DatabaseConfig for a new pool, or pass an existing pool."
            )
        if schema and not pool:
            raise ConfigurationError(
                "Schema override only valid with external pool. "
                "When using DatabaseConfig, set schema in the config object."
            )

        self._external_pool = pool is not None
        self._pool = pool

        if config:
            self.config = config
            self.schema = config.schema_name
        else:
            # Using external pool - create minimal config
            self.config = None  # type: ignore[assignment]
            self.schema = schema or "public"

        self._prepared_statements: dict[str, str] = {}
        self._debug = os.environ.get("DB_DEBUG", "").lower() in ("1", "true", "yes")

    async def connect(self) -> None:
        """
        Initialize connection pool.

        This should be called once at application startup.

        Raises:
            PoolError: If using external pool (cannot connect)
        """
        if self._external_pool:
            raise PoolError(
                "Cannot call connect() when using an external pool. "
                "The pool lifecycle is managed by the pool owner."
            )

        assert self.config is not None

        if self._pool is not None:
            logger.warning("Connection pool already initialized")
            return

        dsn = self.config.get_dsn()
        server_settings = self.config.get_server_settings()

        if self._debug:
            logger.info(
                "Creating connection pool to"
                f" {self.config.host}:{self.config.port}/{self.config.database}"
            )
            logger.info(f"Pool size: {self.config.min_connections}-{self.config.max_connections}")
            logger.info(f"Schema: {self.schema or 'public'}")

        # Implement retry logic for connection pool creation
        delay = self.config.retry_delay

        for attempt in range(self.config.retry_attempts):
            try:
                self._pool = await asyncpg.create_pool(
                    dsn,
                    min_size=self.config.min_connections,
                    max_size=self.config.max_connections,
                    max_queries=self.config.max_queries,
                    max_inactive_connection_lifetime=self.config.max_inactive_connection_lifetime,
                    command_timeout=self.config.command_timeout,
                    server_settings=server_settings,
                    ssl=self.config.build_ssl_context(),
                    init=self._connection_init,
                )
                logger.info("Database connection pool created successfully")
                return
            except (asyncpg.PostgresError, OSError) as e:
                if attempt < self.config.retry_attempts - 1:
                    logger.warning(
                        f"Failed to create connection pool (attempt {attempt + 1}/{self.config.retry_attempts}): {e}"
                        f"\nRetrying in {delay:.1f} seconds..."
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * self.config.retry_backoff, self.config.retry_max_delay)
                else:
                    raise ConnectionError(
                        (
                            "Failed to create connection pool after"
                            f" {self.config.retry_attempts} attempts: {e}"
                        ),
                        host=self.config.host,
                        port=self.config.port,
                        database=self.config.database,
                        attempts=self.config.retry_attempts,
                    ) from e

    async def _connection_init(self, conn: asyncpg.Connection) -> None:
        assert self.config is not None

        """Initialize each connection in the pool."""
        if self.schema:
            await conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema}"')
            await conn.execute(f'SET search_path TO "{self.schema}", public')

        # Run any custom initialization commands
        if self.config.init_commands:
            for cmd in self.config.init_commands:
                await conn.execute(cmd)

        # Prepare frequently used statements
        for name, query in self._prepared_statements.items():
            try:
                await conn.prepare(query, name=name)
                if self._debug:
                    logger.debug(f"Prepared statement '{name}'")
            except Exception as e:
                logger.warning(f"Failed to prepare statement '{name}': {e}")

    async def disconnect(self) -> None:
        """
        Close connection pool.

        This should be called at application shutdown.

        Note: Does nothing if using external pool (caller owns the pool).
        """
        if self._external_pool:
            logger.debug("Using external pool - skipping disconnect")
            return

        if self._pool is None:
            logger.warning("Connection pool not initialized")
            return

        await self._pool.close()
        self._pool = None
        logger.info("Database connection pool closed")

    @classmethod
    async def create_shared_pool(cls, config: DatabaseConfig) -> asyncpg.Pool:
        """
        Create a shared connection pool that can be used by multiple managers.

        Args:
            config: Database configuration for the pool

        Returns:
            Configured asyncpg connection pool

        Example:
            pool = await AsyncDatabaseManager.create_shared_pool(config)
            task_db = AsyncDatabaseManager(pool=pool, schema="task_engine")
            llm_db = AsyncDatabaseManager(pool=pool, schema="llm_service")
        """
        dsn = config.get_dsn()
        server_settings = config.get_server_settings()

        logger.info(
            f"Creating shared connection pool to {config.host}:{config.port}/{config.database}"
        )
        logger.info(f"Pool size: {config.min_connections}-{config.max_connections}")

        # Create a simple init function for shared pools
        async def shared_pool_init(conn: asyncpg.Connection) -> None:
            # Run any custom initialization commands
            if config.init_commands:
                for cmd in config.init_commands:
                    await conn.execute(cmd)

        # Implement retry logic for shared pool creation
        delay = config.retry_delay

        for attempt in range(config.retry_attempts):
            try:
                pool = await asyncpg.create_pool(
                    dsn,
                    min_size=config.min_connections,
                    max_size=config.max_connections,
                    max_queries=config.max_queries,
                    max_inactive_connection_lifetime=config.max_inactive_connection_lifetime,
                    command_timeout=config.command_timeout,
                    server_settings=server_settings,
                    ssl=config.build_ssl_context(),
                    init=shared_pool_init,
                )
                logger.info("Shared connection pool created successfully")
                return pool
            except asyncpg.PostgresError as e:
                if attempt < config.retry_attempts - 1:
                    logger.warning(
                        "Failed to create shared pool "
                        f"(attempt {attempt + 1}/{config.retry_attempts}): {e}"
                        f"\nRetrying in {delay:.1f} seconds..."
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * config.retry_backoff, config.retry_max_delay)
                else:
                    raise ConnectionError(
                        f"Failed to create shared pool after {config.retry_attempts} attempts: {e}",
                        host=config.host,
                        port=config.port,
                        database=config.database,
                        attempts=config.retry_attempts,
                    ) from e

        # This should never be reached due to the raise in the last attempt
        raise ConnectionError("Unexpected error in create_shared_pool")

    def _prepare_query(self, query: str) -> str:
        """
        Prepare query with schema qualification.

        Supports:
        - {{schema}} - replaced with schema name
        - {{tables.tablename}} - replaced with schema.tablename

        Security: Schema and table names are validated to prevent SQL injection.
        """
        # Validate schema name if provided
        if self.schema:
            # PostgreSQL identifier rules: start with letter/underscore,
            # contain letters/numbers/underscores, max 63 chars
            if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$", self.schema):
                raise SchemaError(
                    f"Invalid schema name '{self.schema}'. Schema names must start with a "
                    "letter or underscore and contain only letters, numbers, and underscores.",
                    schema=self.schema,
                )

        if not self.schema:
            # Remove schema placeholders when no schema specified
            query = query.replace("{{schema}}.", "")
            query = query.replace("{{schema}}", "public")
            # Replace table placeholders with just the table name
            query = re.sub(r"{{tables\.([a-zA-Z0-9_]+)}}", r"\1", query)
        else:
            # For safety, quote the schema name
            quoted_schema = f'"{self.schema}"'
            query = query.replace("{{schema}}", quoted_schema)
            # Replace table placeholders with schema-qualified names
            query = re.sub(r"{{tables\.([a-zA-Z0-9_]+)}}", f"{quoted_schema}.\\1", query)

        return query

    def _mask_sensitive_args(self, args: tuple) -> tuple:
        """Mask potentially sensitive arguments for logging."""
        masked = []
        for arg in args:
            if isinstance(arg, str) and len(arg) > 20:
                # Mask long strings that might be passwords or sensitive data
                masked.append(f"{arg[:3]}...{arg[-3:]}" if len(arg) > 6 else "***")
            else:
                masked.append(arg)
        return tuple(masked)

    @asynccontextmanager
    async def acquire(
        self,
    ) -> AsyncIterator[Union[asyncpg.Connection, asyncpg.pool.PoolConnectionProxy]]:
        """
        Acquire a connection from the pool.

        Usage:
            async with db.acquire() as conn:
                await conn.execute(...)
        """
        if not self._pool:
            raise PoolError(
                "Database pool not initialized. Call connect() first, "
                "or ensure the external pool is properly configured."
            )

        async with self._pool.acquire() as connection:
            if self._debug:
                logger.debug(f"Acquired connection {id(connection)}")
            try:
                yield connection
            finally:
                if self._debug:
                    logger.debug(f"Released connection {id(connection)}")

    @asynccontextmanager
    async def transaction(
        self,
    ) -> AsyncIterator[Union[asyncpg.Connection, asyncpg.pool.PoolConnectionProxy]]:
        """
        Execute queries in a transaction.

        Usage:
            async with db.transaction() as conn:
                await conn.execute(...)
                await conn.execute(...)  # All or nothing
        """
        async with self.acquire() as conn:
            if self._debug:
                logger.debug("Starting transaction")
            async with conn.transaction():
                yield conn
            if self._debug:
                logger.debug("Transaction completed")

    async def execute(self, query: str, *args: Any, timeout: Optional[float] = None) -> str:
        """Execute a query without returning results."""
        query = self._prepare_query(query)
        if self._debug:
            # Mask potentially sensitive args in debug logs
            masked_args = self._mask_sensitive_args(args)
            logger.debug(f"Execute: {query[:100]}... Args: {masked_args}")

        try:
            async with self.acquire() as conn:
                if timeout is not None:
                    return await conn.execute(query, *args, timeout=timeout)
                return await conn.execute(query, *args)

        except asyncpg.PostgresError as e:
            raise QueryError(
                "Failed to execute query", query=query, params=args, original_error=e
            ) from e

    async def executemany(self, query: str, args_list: list[tuple]) -> None:
        """Execute a query with multiple parameter sets."""
        query = self._prepare_query(query)
        if self._debug:
            logger.debug(f"Execute many: {query[:100]}... ({len(args_list)} sets)")

        try:
            async with self.acquire() as conn:
                await conn.executemany(query, args_list)
        except asyncpg.PostgresError as e:
            raise QueryError(
                f"Failed to execute batch query with {len(args_list)} parameter sets",
                query=query,
                original_error=e,
            ) from e

    async def fetch_one(
        self, query: str, *args: Any, timeout: Optional[float] = None
    ) -> Optional[dict[str, Any]]:
        """Fetch a single row as a dictionary."""
        query = self._prepare_query(query)
        if self._debug:
            logger.debug(f"Fetch one: {query[:100]}... Args: {args}")

        try:
            async with self.acquire() as conn:
                row = await conn.fetchrow(query, *args, timeout=timeout)
                result = dict(row) if row else None
                if self._debug:
                    logger.debug(f"Result: {result}")
                return result
        except asyncpg.PostgresError as e:
            raise QueryError(
                "Failed to fetch row", query=query, params=args, original_error=e
            ) from e

    async def fetch_all(
        self, query: str, *args: Any, timeout: Optional[float] = None
    ) -> list[dict[str, Any]]:
        """Fetch all rows as a list of dictionaries."""
        query = self._prepare_query(query)
        if self._debug:
            logger.debug(f"Fetch all: {query[:100]}... Args: {args}")

        try:
            async with self.acquire() as conn:
                rows = await conn.fetch(query, *args, timeout=timeout)
                results = [dict(row) for row in rows]
                if self._debug:
                    logger.debug(f"Results: {len(results)} rows")
                return results
        except asyncpg.PostgresError as e:
            raise QueryError(
                "Failed to fetch rows", query=query, params=args, original_error=e
            ) from e

    async def fetch_value(
        self, query: str, *args: Any, column: int = 0, timeout: Optional[float] = None
    ) -> Any:
        """Fetch a single value."""
        query = self._prepare_query(query)
        if self._debug:
            logger.debug(f"Fetch value: {query[:100]}... Args: {args}")

        try:
            async with self.acquire() as conn:
                value = await conn.fetchval(query, *args, column=column, timeout=timeout)
                if self._debug:
                    logger.debug(f"Value: {value}")
                return value
        except asyncpg.PostgresError as e:
            raise QueryError(
                "Failed to fetch value", query=query, params=args, original_error=e
            ) from e

    async def execute_and_return_id(self, query: str, *args: Any) -> Any:
        """Execute an INSERT and return the ID."""
        query = self._prepare_query(query)

        # Ensure RETURNING id clause
        query = query.rstrip(";").rstrip()
        # If the query already contains a RETURNING clause (any case), don't append another
        import re as _re

        if _re.search(r"\bRETURNING\b", query, flags=_re.IGNORECASE) is None:
            query = f"{query} RETURNING id"

        result = await self.fetch_value(query, *args)
        return result

    async def table_exists(self, table_name: str) -> bool:
        """Check if a table exists."""
        schema = self.schema or "public"
        table = table_name

        # Handle already qualified names
        if "." in table_name:
            schema, table = table_name.split(".", 1)

        exists = await self.fetch_value(
            """
            SELECT EXISTS (
                SELECT FROM information_schema.tables
                WHERE table_schema = $1 AND table_name = $2
            )
            """,
            schema,
            table,
        )
        return bool(exists)

    def add_prepared_statement(self, name: str, query: str) -> None:
        """
        Add a prepared statement to be created on each connection.

        Prepared statements improve performance for frequently used queries.
        """
        self._prepared_statements[name] = self._prepare_query(query)

    async def get_pool_stats(self) -> dict[str, Any]:
        """Get connection pool statistics for monitoring."""
        if not self._pool:
            return {"status": "not_connected"}

        # Get pool information
        stats = {
            "status": "connected",
            "min_size": self._pool.get_min_size(),
            "max_size": self._pool.get_max_size(),
            "size": self._pool.get_size(),
            "free_size": self._pool.get_idle_size(),
            "used_size": self._pool.get_size() - self._pool.get_idle_size(),
        }

        # Add database connection info
        try:
            db_info = await self.fetch_one(
                """
                SELECT current_database() as database,
                       current_schema() as schema,
                       pg_backend_pid() as pid,
                       version() as version
                """
            )
            stats.update(db_info or {})
        except Exception as e:
            logger.warning(f"Failed to get database info: {e}")

        return stats

    async def copy_records_to_table(
        self, table_name: str, records: list[tuple], columns: Optional[list[str]] = None
    ) -> int:
        """
        Efficiently copy many records to a table using COPY.

        This is much faster than individual INSERTs for bulk data.
        """
        table_name = self._prepare_query(f"{{{{tables.{table_name}}}}}")

        async with self.acquire() as conn:
            if columns:
                f'COPY {table_name} ({", ".join(columns)}) FROM STDIN'
            else:
                pass

            result = await conn.copy_records_to_table(table_name, records=records, columns=columns)
            # asyncpg returns a string like "COPY 5", extract the number
            if isinstance(result, str) and result.startswith("COPY "):
                return int(result.split()[1])
            return cast(int, result)

    async def fetch_as_model(
        self, model: type[T], query: str, *args: Any, timeout: Optional[float] = None
    ) -> Optional[T]:
        """Fetch a single row and convert to a Pydantic model."""
        data = await self.fetch_one(query, *args, timeout=timeout)
        return model(**data) if data else None

    async def fetch_all_as_model(
        self, model: type[T], query: str, *args: Any, timeout: Optional[float] = None
    ) -> list[T]:
        """Fetch all rows and convert to Pydantic models."""
        rows = await self.fetch_all(query, *args, timeout=timeout)
        return [model(**row) for row in rows]


class SchemaManager:
    """Manages database schemas for multi-module usage."""

    def __init__(self, db_manager: AsyncDatabaseManager):
        self.db = db_manager
        self.schema_name = db_manager.schema

    async def ensure_schema_exists(self) -> None:
        """Create the schema if it doesn't exist."""
        if not self.schema_name:
            return

        await self.db.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema_name}"')
        logger.info(f"Ensured schema '{self.schema_name}' exists")

    def qualify_table_name(self, table_name: str) -> str:
        """Qualify a table name with the schema if specified."""
        if not self.schema_name:
            return table_name
        return f"{self.schema_name}.{table_name}"
