"""Shared database manager for all microservices."""

import asyncio
import os
from pathlib import Path
from typing import ClassVar, Optional

import asyncpg

from pgdbm import AsyncDatabaseManager, AsyncMigrationManager, DatabaseConfig


class SharedDatabaseManager:
    """Singleton database manager shared across all services."""

    _instance: ClassVar[Optional["SharedDatabaseManager"]] = None
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()
    _pool: Optional[asyncpg.Pool] = None
    _db_manager: Optional[AsyncDatabaseManager] = None
    _initialized: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def initialize(self, database_url: Optional[str] = None) -> None:
        """Initialize the shared database connection pool."""
        if self._initialized:
            return

        async with self._lock:
            if self._initialized:
                return

            # Get database URL
            db_url = database_url or os.environ.get("DATABASE_URL")
            if not db_url:
                raise ValueError("DATABASE_URL environment variable not set")

            # Create database configuration
            config = DatabaseConfig(connection_string=db_url)

            # Adjust pool size for microservices
            # Total connections = min_connections * number_of_services
            config.min_connections = 2  # Minimum per service
            config.max_connections = 10  # Maximum per service

            # Create shared pool first
            self._pool = await AsyncDatabaseManager.create_shared_pool(config)

            # Initialize database manager with the pool
            self._db_manager = AsyncDatabaseManager(pool=self._pool)

            self._initialized = True
            print(
                f"Shared database pool initialized with {config.min_connections}-{config.max_connections} connections"
            )

    async def close(self) -> None:
        """Close the shared database connection pool."""
        if self._pool:
            await self._pool.close()
            self._initialized = False
            self._pool = None
            self._db_manager = None

    def get_manager(self) -> AsyncDatabaseManager:
        """Get the database manager instance."""
        if not self._initialized or not self._db_manager:
            raise RuntimeError("SharedDatabaseManager not initialized")
        return self._db_manager

    def get_pool(self) -> asyncpg.Pool:
        """Get the shared connection pool (for testing)."""
        if not self._initialized or not self._pool:
            raise RuntimeError("SharedDatabaseManager not initialized")
        return self._pool

    @classmethod
    async def get_instance(cls) -> "SharedDatabaseManager":
        """Get or create the singleton instance."""
        if cls._instance is None:
            cls._instance = cls()

        if not cls._instance._initialized:
            await cls._instance.initialize()

        return cls._instance

    async def run_migrations(self) -> None:
        """Run database migrations."""
        if not self._db_manager:
            raise RuntimeError("Database not initialized")

        migrations_path = Path(__file__).parent.parent / "migrations"
        migration_manager = AsyncMigrationManager(self._db_manager, str(migrations_path))
        await migration_manager.apply_pending_migrations()
        print("Database migrations completed")


class ServiceDatabase:
    """Base database wrapper for individual services with schema isolation."""

    def __init__(self, service_name: str, schema_name: str):
        """Initialize service database wrapper with schema isolation.

        Args:
            service_name: Name of the service (for logging)
            schema_name: PostgreSQL schema name for this service's tables
        """
        self.service_name = service_name
        self.schema_name = schema_name
        self.db: Optional[AsyncDatabaseManager] = None
        self._migrations_path = (
            Path(__file__).parent.parent / "services" / schema_name / "migrations"
        )

    async def initialize(self) -> None:
        """Initialize database connection using shared pool with schema isolation."""
        shared = await SharedDatabaseManager.get_instance()
        # Create schema-isolated database manager
        self.db = AsyncDatabaseManager(pool=shared._pool, schema=self.schema_name)

        # Create schema if it doesn't exist
        await shared._db_manager.execute(f'CREATE SCHEMA IF NOT EXISTS "{self.schema_name}"')

        # Run service-specific migrations
        if self._migrations_path.exists():
            migrations = AsyncMigrationManager(
                self.db,
                migrations_path=str(self._migrations_path),
                module_name=self.schema_name,  # Use schema name as module name
            )
            result = await migrations.apply_pending_migrations()
            if result["applied"]:
                print(f"{self.service_name}: Applied {len(result['applied'])} migrations")

        print(f"{self.service_name} initialized with schema: {self.schema_name}")

    async def execute(self, query: str, *args):
        """Execute a query."""
        if not self.db:
            raise RuntimeError(f"{self.service_name} database not initialized")
        return await self.db.execute(query, *args)

    async def fetch_one(self, query: str, *args):
        """Fetch one row."""
        if not self.db:
            raise RuntimeError(f"{self.service_name} database not initialized")
        return await self.db.fetch_one(query, *args)

    async def fetch_all(self, query: str, *args):
        """Fetch all rows."""
        if not self.db:
            raise RuntimeError(f"{self.service_name} database not initialized")
        return await self.db.fetch_all(query, *args)

    def transaction(self):
        """Get a transaction context."""
        if not self.db:
            raise RuntimeError(f"{self.service_name} database not initialized")
        return self.db.transaction()


# Service registry functions
async def register_service(
    service_name: str, service_url: str, health_check_url: Optional[str] = None
) -> None:
    """Register a service in the registry."""
    shared = await SharedDatabaseManager.get_instance()
    db = shared.get_manager()

    if not health_check_url:
        health_check_url = f"{service_url}/health"

    await db.execute(
        """
        INSERT INTO service_registry (service_name, service_url, health_check_url)
        VALUES ($1, $2, $3)
        ON CONFLICT (service_name)
        DO UPDATE SET
            service_url = EXCLUDED.service_url,
            health_check_url = EXCLUDED.health_check_url,
            last_heartbeat = NOW(),
            is_healthy = TRUE
    """,
        service_name,
        service_url,
        health_check_url,
    )

    print(f"Service '{service_name}' registered at {service_url}")


async def discover_service(service_name: str) -> Optional[str]:
    """Discover a service URL from the registry."""
    shared = await SharedDatabaseManager.get_instance()
    db = shared.get_manager()

    result = await db.fetch_one(
        """
        SELECT service_url
        FROM service_registry
        WHERE service_name = $1 AND is_healthy = TRUE
    """,
        service_name,
    )

    return result["service_url"] if result else None


async def update_service_health(service_name: str, is_healthy: bool) -> None:
    """Update service health status."""
    shared = await SharedDatabaseManager.get_instance()
    db = shared.get_manager()

    await db.execute(
        """
        UPDATE service_registry
        SET is_healthy = $2, last_heartbeat = NOW()
        WHERE service_name = $1
    """,
        service_name,
        is_healthy,
    )
