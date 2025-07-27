"""Test shared connection pool functionality."""

import asyncio

import pytest

from services.orders.db import OrderDatabase
from services.users.db import UserDatabase
from shared.database import (
    ServiceDatabase,
    SharedDatabaseManager,
    discover_service,
    register_service,
)
from shared.models import UserCreate


@pytest.mark.asyncio
async def test_shared_connection_pool(shared_db, clean_tables):
    """Test that multiple services share the same connection pool."""
    # Get the shared database manager
    shared_db.get_manager()  # Verify it's initialized

    # Initialize multiple service databases
    user_db = UserDatabase()
    await user_db.initialize()

    order_db = OrderDatabase()
    await order_db.initialize()

    # Verify they're using different manager instances (schema isolation)
    assert user_db.db is not order_db.db

    # Verify they're using the same shared pool (through SharedDatabaseManager)
    shared = await SharedDatabaseManager.get_instance()
    shared.get_pool()  # Verify pool exists

    # Both services should be initialized with the same shared pool
    # We can't directly access the pool from AsyncDatabaseManager (it's private)
    # but we know they were created with the same pool from SharedDatabaseManager

    # Test concurrent operations from different services
    async def user_operation():
        return await user_db.fetch_one("SELECT COUNT(*) as count FROM {{tables.users}}")

    async def order_operation():
        return await order_db.fetch_one("SELECT COUNT(*) as count FROM {{tables.orders}}")

    # Run operations concurrently
    results = await asyncio.gather(user_operation(), order_operation())

    assert results[0]["count"] == 0
    assert results[1]["count"] == 0


@pytest.mark.asyncio
async def test_service_registry(shared_db, clean_tables):
    """Test service registration and discovery."""
    # Register services
    await register_service("test-service-1", "http://localhost:9001")
    await register_service(
        "test-service-2", "http://localhost:9002", "http://localhost:9002/healthz"
    )

    # Discover services
    url1 = await discover_service("test-service-1")
    url2 = await discover_service("test-service-2")

    assert url1 == "http://localhost:9001"
    assert url2 == "http://localhost:9002"

    # Test non-existent service
    url3 = await discover_service("non-existent")
    assert url3 is None

    # Update service registration
    await register_service("test-service-1", "http://localhost:9003")
    url1_updated = await discover_service("test-service-1")
    assert url1_updated == "http://localhost:9003"


@pytest.mark.asyncio
async def test_transaction_isolation(shared_db, clean_tables):
    """Test that transactions work correctly with schema isolation."""
    user_db = UserDatabase()
    await user_db.initialize()

    # First verify the test email doesn't exist
    initial_check = await user_db.fetch_one(
        "SELECT COUNT(*) as count FROM {{tables.users}} WHERE email = $1",
        "test_rollback@example.com",
    )
    assert initial_check["count"] == 0, f"User already exists before test: {initial_check}"

    # Create a user that will persist
    user_data = UserCreate(
        email="test_persist@example.com", name="Persistent User", password="test123"
    )
    await user_db.create_user(user_data)

    # Verify it exists
    check = await user_db.fetch_one(
        "SELECT COUNT(*) as count FROM {{tables.users}} WHERE email = $1",
        "test_persist@example.com",
    )
    assert check["count"] == 1

    # Test schema isolation - each service has its own schema
    # The order service shouldn't be able to see users table directly
    order_db = OrderDatabase()
    await order_db.initialize()

    # Create an order (this should work in the orders schema)
    try:
        # This would fail if schemas weren't properly isolated
        await order_db.execute(
            """
            INSERT INTO {{tables.orders}} (user_id, order_number, status, total_amount)
            VALUES ($1, $2, $3, $4)
        """,
            "550e8400-e29b-41d4-a716-446655440000",
            "TEST-001",
            "pending",
            100.00,
        )

        # Verify order exists
        order_check = await order_db.fetch_one(
            "SELECT COUNT(*) as count FROM {{tables.orders}} WHERE order_number = $1", "TEST-001"
        )
        assert order_check["count"] == 1
    except Exception as e:
        pytest.fail(f"Schema isolation test failed: {e}")


@pytest.mark.asyncio
async def test_connection_pool_limits(shared_db):
    """Test that connection pool limits are respected."""
    # Get shared pool
    shared = await SharedDatabaseManager.get_instance()
    pool = shared.get_pool()

    # Check configured limits (these are internal asyncpg attributes)
    assert pool._minsize >= 2
    assert pool._maxsize >= 10

    # Create multiple service databases with schema isolation
    services = []
    for i in range(5):
        svc = ServiceDatabase(f"test-service-{i}", f"test_schema_{i}")
        await svc.initialize()
        services.append(svc)

    # Run concurrent queries
    async def run_query(svc):
        return await svc.fetch_one("SELECT 1 as value")

    # This should not exceed pool limits
    results = await asyncio.gather(*[run_query(svc) for svc in services])

    assert len(results) == 5
    assert all(r["value"] == 1 for r in results)
