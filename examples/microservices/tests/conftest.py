"""Test configuration for microservices."""

import os

import pytest

# Set test environment
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://test:test@localhost/test_microservices"
)

# Import base fixtures from pgdbm
from pgdbm.fixtures.conftest import test_db_factory  # noqa: F401 - used by pytest
from shared.database import SharedDatabaseManager


@pytest.fixture
async def shared_db(test_db_factory) -> SharedDatabaseManager:  # noqa: F811
    """Get shared database manager for tests."""
    # Create a test database
    test_db = await test_db_factory.create_db(suffix="microservices")

    # Initialize shared database manager with test database connection string
    shared = SharedDatabaseManager()
    # Get the connection string from the test database manager
    dsn = test_db.config.get_dsn()
    await shared.initialize(dsn)

    # Run migrations
    await shared.run_migrations()

    yield shared

    await shared.close()


@pytest.fixture
async def clean_tables(shared_db):
    """Clean all tables before each test."""
    db = shared_db.get_manager()

    # Truncate tables in each schema
    # Note: With schema isolation, each service has its own tables
    schemas_tables = [
        ("public", ["events", "circuit_breakers", "service_registry"]),
        ("users", ["users"]),
        ("orders", ["order_items", "orders"]),
        ("inventory", ["stock_reservations", "products"]),
    ]

    for schema, tables in schemas_tables:
        for table in tables:
            table_name = f"{schema}.{table}" if schema != "public" else table
            try:
                await db.execute(f"TRUNCATE TABLE {table_name} CASCADE")
            except Exception:
                # Table might not exist if migrations haven't run for that service
                pass

    yield
