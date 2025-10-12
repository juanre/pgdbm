"""Database infrastructure with shared pool pattern."""

import logging
from typing import TYPE_CHECKING, Optional

from app.config import settings
from pgdbm import AsyncDatabaseManager, DatabaseConfig
from pgdbm.migrations import AsyncMigrationManager

if TYPE_CHECKING:
    import asyncpg

logger = logging.getLogger(__name__)


class DatabaseInfrastructure:
    """
    Singleton managing the shared database pool and service-specific managers.

    This implements the recommended shared pool pattern where all services
    share a single connection pool but use different schemas for isolation.
    """

    _instance: Optional["DatabaseInfrastructure"] = None
    _initialized: bool = False

    def __new__(cls) -> "DatabaseInfrastructure":
        """Ensure singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the infrastructure (only runs once due to singleton)."""
        if not self._initialized:
            self.shared_pool: Optional[asyncpg.Pool] = None
            self.managers: dict[str, AsyncDatabaseManager] = {}
            self._initialized = True

    async def initialize(self) -> None:
        """
        Initialize the shared pool and create service managers.

        This should be called once during application startup.
        """
        if self.shared_pool is not None:
            logger.warning("Database infrastructure already initialized")
            return

        logger.info("Initializing database infrastructure")

        # Create configuration
        config = DatabaseConfig(
            connection_string=settings.database_url,
            min_connections=settings.database_min_connections,
            max_connections=settings.database_max_connections,
            command_timeout=settings.database_command_timeout,
            ssl_enabled=settings.database_ssl_enabled,
        )

        # Create the shared pool (ONE pool for entire application)
        self.shared_pool = await AsyncDatabaseManager.create_shared_pool(config)
        logger.info(
            f"Created shared connection pool: "
            f"{settings.database_min_connections}-{settings.database_max_connections} connections"
        )

        # Create schema-specific managers (they share the pool)
        self.managers = {
            "users": AsyncDatabaseManager(pool=self.shared_pool, schema="users"),
            "orders": AsyncDatabaseManager(pool=self.shared_pool, schema="orders"),
            "analytics": AsyncDatabaseManager(pool=self.shared_pool, schema="analytics"),
        }

        logger.info(
            f"Created {len(self.managers)} service managers with schemas: {list(self.managers.keys())}"
        )

        # Run migrations for each schema
        await self._run_migrations()

    async def _run_migrations(self) -> None:
        """Run migrations for all schemas."""
        logger.info("Running database migrations")

        for service_name, db_manager in self.managers.items():
            try:
                migrations = AsyncMigrationManager(
                    db_manager,
                    migrations_path=f"migrations/{service_name}",
                    module_name=service_name,
                )

                result = await migrations.apply_pending_migrations()

                if result["applied"]:
                    logger.info(
                        f"Applied {len(result['applied'])} migrations for {service_name}: "
                        f"{[m['filename'] for m in result['applied']]}"
                    )
                else:
                    logger.info(f"No pending migrations for {service_name}")

            except Exception as e:
                logger.error(f"Failed to run migrations for {service_name}: {e}")
                raise

    async def close(self) -> None:
        """Close the shared pool and cleanup resources."""
        if self.shared_pool:
            logger.info("Closing shared connection pool")
            await self.shared_pool.close()
            self.shared_pool = None
            self.managers.clear()

    def get_manager(self, service: str) -> AsyncDatabaseManager:
        """
        Get the database manager for a specific service.

        Args:
            service: Service name (e.g., 'users', 'orders', 'analytics')

        Returns:
            AsyncDatabaseManager for the service

        Raises:
            ValueError: If service not found
        """
        if service not in self.managers:
            raise ValueError(f"Unknown service: {service}. Available: {list(self.managers.keys())}")
        return self.managers[service]

    async def health_check(self) -> dict[str, bool]:
        """
        Perform health check on all database connections.

        Returns:
            Dict mapping service names to health status
        """
        health = {}

        for service, manager in self.managers.items():
            try:
                # Simple query to test connection
                await manager.fetch_value("SELECT 1")
                health[service] = True
            except Exception as e:
                logger.error(f"Health check failed for {service}: {e}")
                health[service] = False

        return health

    def get_pool_stats(self) -> dict[str, int]:
        """
        Get connection pool statistics.

        Returns:
            Pool statistics including active/idle connections
        """
        if not self.shared_pool:
            return {
                "min_size": 0,
                "max_size": 0,
                "size": 0,
                "free_size": 0,
                "used_size": 0,
            }

        return {
            "min_size": self.shared_pool._minsize,
            "max_size": self.shared_pool._maxsize,
            "size": self.shared_pool._size,
            "free_size": self.shared_pool._freesize,
            "used_size": self.shared_pool._size - self.shared_pool._freesize,
        }


# Global database infrastructure instance
db_infrastructure = DatabaseInfrastructure()
