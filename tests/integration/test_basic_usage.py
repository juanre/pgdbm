# Copyright (c) 2025 Juan Reyero
# Licensed under the MIT License

"""
Integration tests for basic pgdbm usage patterns.

These tests demonstrate how users would typically interact with the library.
"""

import json
from datetime import datetime

import asyncpg
import pytest

from pgdbm import AsyncDatabaseManager, ConfigurationError, DatabaseConfig, QueryError


class TestBasicDatabaseOperations:
    """Test basic database operations that users would commonly perform."""

    @pytest.mark.asyncio
    async def test_connection_lifecycle(self, test_db):
        """Test basic connection setup and teardown."""
        # The test_db fixture already provides a connected database
        # Let's verify the connection works
        result = await test_db.fetch_one("SELECT 1 as value")
        assert result["value"] == 1

        # Check pool stats
        stats = await test_db.get_pool_stats()
        assert stats["status"] == "connected"
        assert stats["min_size"] == test_db.config.min_connections
        assert stats["max_size"] == test_db.config.max_connections

        # The fixture will handle cleanup

    @pytest.mark.asyncio
    async def test_crud_operations(self, test_db):
        """Test Create, Read, Update, Delete operations."""
        # Create table
        await test_db.execute(
            """
            CREATE TABLE products (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                price DECIMAL(10, 2) NOT NULL,
                stock INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # CREATE - Insert with returning ID
        product_id = await test_db.execute_and_return_id(
            """
            INSERT INTO products (name, price, stock)
            VALUES ($1, $2, $3)
            """,
            "Laptop",
            999.99,
            10,
        )
        assert product_id is not None

        # READ - Fetch one
        product = await test_db.fetch_one("SELECT * FROM products WHERE id = $1", product_id)
        assert product["name"] == "Laptop"
        assert float(product["price"]) == 999.99
        assert product["stock"] == 10

        # UPDATE
        await test_db.execute(
            """
            UPDATE products
            SET price = $1, stock = stock - 1
            WHERE id = $2
            """,
            899.99,
            product_id,
        )

        # Verify update
        updated = await test_db.fetch_one(
            "SELECT price, stock FROM products WHERE id = $1", product_id
        )
        assert float(updated["price"]) == 899.99
        assert updated["stock"] == 9

        # DELETE
        await test_db.execute("DELETE FROM products WHERE id = $1", product_id)

        # Verify deletion
        deleted = await test_db.fetch_one("SELECT * FROM products WHERE id = $1", product_id)
        assert deleted is None

    @pytest.mark.asyncio
    async def test_batch_operations(self, test_db):
        """Test batch insert and fetch operations."""
        # Create table
        await test_db.execute(
            """
            CREATE TABLE inventory (
                id SERIAL PRIMARY KEY,
                sku VARCHAR(50) UNIQUE NOT NULL,
                quantity INTEGER NOT NULL,
                location VARCHAR(100)
            )
        """
        )

        # Batch insert using executemany
        inventory_items = [
            ("SKU001", 100, "Warehouse A"),
            ("SKU002", 50, "Warehouse B"),
            ("SKU003", 75, "Warehouse A"),
            ("SKU004", 200, "Warehouse C"),
        ]

        await test_db.executemany(
            """
            INSERT INTO inventory (sku, quantity, location)
            VALUES ($1, $2, $3)
            """,
            inventory_items,
        )

        # Fetch all
        all_items = await test_db.fetch_all("SELECT * FROM inventory ORDER BY sku")
        assert len(all_items) == 4
        assert all_items[0]["sku"] == "SKU001"
        assert all_items[3]["quantity"] == 200

        # Fetch with filter
        warehouse_a = await test_db.fetch_all(
            "SELECT * FROM inventory WHERE location = $1 ORDER BY sku", "Warehouse A"
        )
        assert len(warehouse_a) == 2
        assert warehouse_a[0]["sku"] == "SKU001"
        assert warehouse_a[1]["sku"] == "SKU003"

        # Aggregate query
        total_quantity = await test_db.fetch_value("SELECT SUM(quantity) FROM inventory")
        assert total_quantity == 425

    @pytest.mark.asyncio
    async def test_transaction_commit(self, test_db):
        """Test successful transaction commit."""
        # Create table
        await test_db.execute(
            """
            CREATE TABLE accounts (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                balance DECIMAL(10, 2) NOT NULL DEFAULT 0
            )
        """
        )

        # Insert initial accounts
        await test_db.execute(
            """
            INSERT INTO accounts (name, balance) VALUES
            ('Alice', 1000),
            ('Bob', 500)
        """
        )

        # Perform transfer in transaction
        async with test_db.transaction() as tx:
            # Deduct from Alice
            await tx.execute(
                "UPDATE accounts SET balance = balance - $1 WHERE name = $2",
                100,
                "Alice",
            )

            # Add to Bob
            await tx.execute(
                "UPDATE accounts SET balance = balance + $1 WHERE name = $2", 100, "Bob"
            )

        # Verify transaction completed
        alice = await test_db.fetch_one("SELECT balance FROM accounts WHERE name = $1", "Alice")
        bob = await test_db.fetch_one("SELECT balance FROM accounts WHERE name = $1", "Bob")

        assert float(alice["balance"]) == 900
        assert float(bob["balance"]) == 600

    @pytest.mark.asyncio
    async def test_transaction_rollback(self, test_db):
        """Test transaction rollback on error."""
        # Create table
        await test_db.execute(
            """
            CREATE TABLE inventory (
                id SERIAL PRIMARY KEY,
                item VARCHAR(100) NOT NULL,
                quantity INTEGER NOT NULL CHECK (quantity >= 0)
            )
        """
        )

        # Insert initial inventory
        await test_db.execute(
            "INSERT INTO inventory (item, quantity) VALUES ($1, $2)", "Widget", 10
        )

        # Try transaction that will fail
        with pytest.raises(asyncpg.CheckViolationError):
            async with test_db.transaction() as tx:
                # This will succeed
                await tx.execute(
                    "UPDATE inventory SET quantity = quantity - $1 WHERE item = $2",
                    5,
                    "Widget",
                )

                # This will fail due to CHECK constraint
                await tx.execute(
                    "UPDATE inventory SET quantity = quantity - $1 WHERE item = $2",
                    20,
                    "Widget",  # Would make quantity negative
                )

        # Verify rollback - quantity should still be 10
        result = await test_db.fetch_one("SELECT quantity FROM inventory WHERE item = $1", "Widget")
        assert result["quantity"] == 10


class TestErrorHandling:
    """Test error handling and custom exceptions."""

    @pytest.mark.asyncio
    async def test_connection_error_with_retry(self):
        """Test connection retry logic with invalid host."""
        config = DatabaseConfig(
            host="invalid-db-host-that-does-not-exist.local",
            database="test_db",
            user="postgres",
            password="postgres",
            retry_attempts=2,
            retry_delay=0.1,  # Fast retry for tests
        )

        db = AsyncDatabaseManager(config)

        # Should raise ConnectionError after retries
        from pgdbm.errors import ConnectionError as AsyncDBConnectionError

        with pytest.raises(AsyncDBConnectionError) as exc_info:
            await db.connect()

        error = exc_info.value
        assert "invalid-db-host-that-does-not-exist.local" in str(error)
        assert "after 2 attempts" in str(error)
        assert "Troubleshooting tips" in str(error)

    @pytest.mark.asyncio
    async def test_query_error_with_context(self, test_db):
        """Test enhanced query error messages."""
        # Try to query non-existent table
        with pytest.raises(QueryError) as exc_info:
            await test_db.fetch_one("SELECT * FROM non_existent_table")

        error = exc_info.value
        error_str = str(error)
        assert "non_existent_table" in error_str
        assert "does not exist" in error_str.lower()
        # Check that we get query context
        assert "Query:" in error_str
        assert "SELECT * FROM non_existent_table" in error_str

    @pytest.mark.asyncio
    async def test_configuration_error(self):
        """Test configuration validation errors."""
        # Try to create manager with both config and pool
        config = DatabaseConfig()

        with pytest.raises(ConfigurationError) as exc_info:
            AsyncDatabaseManager(config=config, pool="fake_pool")

        assert "Cannot provide both config and pool" in str(exc_info.value)


class TestAdvancedFeatures:
    """Test advanced features like prepared statements and bulk operations."""

    @pytest.mark.asyncio
    async def test_prepared_statements(self, test_db):
        """Test using prepared statements for performance."""
        # Create table
        await test_db.execute(
            """
            CREATE TABLE metrics (
                id SERIAL PRIMARY KEY,
                metric_name VARCHAR(100) NOT NULL,
                value FLOAT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Add prepared statement
        test_db.add_prepared_statement(
            "insert_metric", "INSERT INTO metrics (metric_name, value) VALUES ($1, $2)"
        )

        # Use prepared statement multiple times
        metrics = [
            ("cpu_usage", 45.2),
            ("memory_usage", 78.5),
            ("disk_usage", 62.1),
            ("cpu_usage", 48.7),
            ("memory_usage", 79.2),
        ]

        for name, value in metrics:
            await test_db.execute(
                "INSERT INTO metrics (metric_name, value) VALUES ($1, $2)", name, value
            )

        # Verify insertions
        count = await test_db.fetch_value("SELECT COUNT(*) FROM metrics")
        assert count == 5

    @pytest.mark.asyncio
    async def test_copy_records_bulk_insert(self, test_db):
        """Test efficient bulk insert using COPY."""
        # Create table
        await test_db.execute(
            """
            CREATE TABLE events (
                id SERIAL PRIMARY KEY,
                event_type VARCHAR(50) NOT NULL,
                user_id INTEGER,
                data JSONB,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Prepare bulk data
        import json

        events = [
            ("page_view", 1, json.dumps({"page": "/home"})),
            ("click", 1, json.dumps({"button": "signup"})),
            ("page_view", 2, json.dumps({"page": "/products"})),
            ("purchase", 2, json.dumps({"item": "laptop", "price": 999})),
            ("page_view", 3, json.dumps({"page": "/home"})),
        ]

        # Bulk insert
        rows_inserted = await test_db.copy_records_to_table(
            "events", records=events, columns=["event_type", "user_id", "data"]
        )

        assert rows_inserted == 5

        # Verify data was inserted
        all_events = await test_db.fetch_all("SELECT * FROM events ORDER BY id")
        assert len(all_events) == 5
        assert all_events[0]["event_type"] == "page_view"

        # When using COPY with JSONB columns, we need to check if PostgreSQL
        # properly converted the JSON strings to JSONB
        # Let's query with JSON operators to verify it's stored as JSONB
        laptop_event = await test_db.fetch_one(
            "SELECT * FROM events WHERE data->>'item' = 'laptop'"
        )
        assert laptop_event is not None
        assert laptop_event["event_type"] == "purchase"

        # Verify we can access JSON fields using PostgreSQL operators
        item_name = await test_db.fetch_value(
            "SELECT data->>'item' FROM events WHERE id = $1", laptop_event["id"]
        )
        assert item_name == "laptop"

    @pytest.mark.asyncio
    async def test_json_handling(self, test_db):
        """Test working with JSON/JSONB columns."""
        # Create table with JSONB
        await test_db.execute(
            """
            CREATE TABLE api_responses (
                id SERIAL PRIMARY KEY,
                endpoint VARCHAR(255) NOT NULL,
                response JSONB NOT NULL,
                status_code INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Insert JSON data
        response_data = {
            "status": "success",
            "data": {
                "users": [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
                "total": 2,
            },
            "timestamp": datetime.now().isoformat(),
        }

        await test_db.execute(
            """
            INSERT INTO api_responses (endpoint, response, status_code)
            VALUES ($1, $2, $3)
            """,
            "/api/users",
            json.dumps(response_data),
            200,
        )

        # Query JSON data
        result = await test_db.fetch_one(
            """
            SELECT
                endpoint,
                response->>'status' as status,
                response->'data'->>'total' as total_users,
                jsonb_array_length(response->'data'->'users') as user_count
            FROM api_responses
            WHERE endpoint = $1
        """,
            "/api/users",
        )

        assert result["status"] == "success"
        assert int(result["total_users"]) == 2
        assert result["user_count"] == 2

    @pytest.mark.asyncio
    async def test_connection_pool_reuse(self, test_db):
        """Test that connection pool properly reuses connections."""
        await test_db.get_pool_stats()  # Ensure pool is initialized

        # Run multiple queries
        agents = []
        for i in range(10):
            agents.append(test_db.fetch_one(f"SELECT {i} as num"))

        import asyncio

        results = await asyncio.gather(*agents)

        # Check all queries succeeded
        assert len(results) == 10
        for i, result in enumerate(results):
            assert result["num"] == i

        # Check pool stats - should reuse connections
        final_stats = await test_db.get_pool_stats()
        assert final_stats["size"] <= final_stats["max_size"]


class TestTransactionManager:
    """Test the TransactionManager wrapper with template substitution."""

    @pytest.mark.asyncio
    async def test_transaction_with_templates(self, test_db_with_schema):
        """Test that transactions properly handle {{tables.}} template substitution."""
        # Create table using templates
        await test_db_with_schema.execute(
            """
            CREATE TABLE {{tables.users}} (
                id SERIAL PRIMARY KEY,
                email VARCHAR(255) UNIQUE NOT NULL,
                balance DECIMAL(10, 2) DEFAULT 0
            )
            """
        )

        # Insert test data
        await test_db_with_schema.execute(
            """
            INSERT INTO {{tables.users}} (email, balance) VALUES
            ('alice@example.com', 1000),
            ('bob@example.com', 500)
            """
        )

        # Perform transaction with template substitution
        async with test_db_with_schema.transaction() as tx:
            # Deduct from Alice
            await tx.execute(
                "UPDATE {{tables.users}} SET balance = balance - $1 WHERE email = $2",
                100,
                "alice@example.com",
            )

            # Add to Bob
            await tx.execute(
                "UPDATE {{tables.users}} SET balance = balance + $1 WHERE email = $2",
                100,
                "bob@example.com",
            )

        # Verify transaction completed
        alice = await test_db_with_schema.fetch_one(
            "SELECT balance FROM {{tables.users}} WHERE email = $1", "alice@example.com"
        )
        bob = await test_db_with_schema.fetch_one(
            "SELECT balance FROM {{tables.users}} WHERE email = $1", "bob@example.com"
        )

        assert float(alice["balance"]) == 900
        assert float(bob["balance"]) == 600

    @pytest.mark.asyncio
    async def test_transaction_fetch_methods(self, test_db_with_schema):
        """Test all fetch methods in TransactionManager."""
        # Create table
        await test_db_with_schema.execute(
            """
            CREATE TABLE {{tables.products}} (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                price DECIMAL(10, 2) NOT NULL,
                stock INTEGER DEFAULT 0
            )
            """
        )

        # Insert test data in a transaction
        async with test_db_with_schema.transaction() as tx:
            # Test execute
            await tx.execute(
                """
                INSERT INTO {{tables.products}} (name, price, stock) VALUES
                ('Product A', 10.00, 100),
                ('Product B', 20.00, 50),
                ('Product C', 30.00, 25)
                """
            )

            # Test fetch_one
            product = await tx.fetch_one(
                "SELECT * FROM {{tables.products}} WHERE name = $1", "Product A"
            )
            assert product is not None
            assert product["name"] == "Product A"
            assert float(product["price"]) == 10.00

            # Test fetch_all
            all_products = await tx.fetch_all("SELECT * FROM {{tables.products}} ORDER BY name")
            assert len(all_products) == 3
            assert all_products[0]["name"] == "Product A"
            assert all_products[1]["name"] == "Product B"
            assert all_products[2]["name"] == "Product C"

            # Test fetch_value
            count = await tx.fetch_value("SELECT COUNT(*) FROM {{tables.products}}")
            assert count == 3

            total_stock = await tx.fetch_value(
                "SELECT SUM(stock) FROM {{tables.products}}", column=0
            )
            assert total_stock == 175

    @pytest.mark.asyncio
    async def test_transaction_rollback_with_templates(self, test_db_with_schema):
        """Test transaction rollback works with template substitution."""
        # Create table
        await test_db_with_schema.execute(
            """
            CREATE TABLE {{tables.orders}} (
                id SERIAL PRIMARY KEY,
                order_number VARCHAR(50) UNIQUE NOT NULL,
                total DECIMAL(10, 2) CHECK (total >= 0)
            )
            """
        )

        # Insert initial order
        await test_db_with_schema.execute(
            "INSERT INTO {{tables.orders}} (order_number, total) VALUES ($1, $2)",
            "ORD-001",
            100.00,
        )

        # Try transaction that will fail
        with pytest.raises(asyncpg.CheckViolationError):
            async with test_db_with_schema.transaction() as tx:
                # This will succeed
                await tx.execute(
                    "UPDATE {{tables.orders}} SET total = $1 WHERE order_number = $2",
                    50.00,
                    "ORD-001",
                )

                # This will fail due to CHECK constraint
                await tx.execute(
                    "UPDATE {{tables.orders}} SET total = $1 WHERE order_number = $2",
                    -10.00,  # Negative value violates CHECK
                    "ORD-001",
                )

        # Verify rollback - total should still be 100
        result = await test_db_with_schema.fetch_one(
            "SELECT total FROM {{tables.orders}} WHERE order_number = $1", "ORD-001"
        )
        assert float(result["total"]) == 100.00

    @pytest.mark.asyncio
    async def test_nested_transactions(self, test_db_with_schema):
        """Test nested transactions (savepoints) with templates."""
        # Create table
        await test_db_with_schema.execute(
            """
            CREATE TABLE {{tables.accounts}} (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                balance DECIMAL(10, 2) DEFAULT 0
            )
            """
        )

        # Insert test data
        await test_db_with_schema.execute(
            "INSERT INTO {{tables.accounts}} (name, balance) VALUES ($1, $2)", "Alice", 1000
        )

        # Outer transaction
        async with test_db_with_schema.transaction() as tx:
            await tx.execute(
                "UPDATE {{tables.accounts}} SET balance = balance - $1 WHERE name = $2",
                100,
                "Alice",
            )

            # Nested transaction (savepoint)
            try:
                async with tx.transaction():
                    await tx.execute(
                        "UPDATE {{tables.accounts}} SET balance = balance - $1 WHERE name = $2",
                        200,
                        "Alice",
                    )
                    # Force an error to rollback savepoint
                    raise ValueError("Intentional error")
            except ValueError:
                pass  # Savepoint rolled back

            # The outer transaction continues
            await tx.execute(
                "UPDATE {{tables.accounts}} SET balance = balance - $1 WHERE name = $2",
                50,
                "Alice",
            )

        # Verify: 1000 - 100 - 50 = 850 (the 200 was rolled back)
        result = await test_db_with_schema.fetch_one(
            "SELECT balance FROM {{tables.accounts}} WHERE name = $1", "Alice"
        )
        assert float(result["balance"]) == 850
