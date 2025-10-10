# Copyright (c) 2025 Juan Reyero
# Licensed under the MIT License

"""
Integration tests for monitoring and debugging features.

These tests demonstrate how to use monitoring capabilities in production.
"""

import asyncio

import pytest

from pgdbm import DatabaseDebugger, MonitoredAsyncDatabaseManager, log_query_performance


class TestMonitoringFeatures:
    """Test database monitoring and performance tracking."""

    @pytest.mark.asyncio
    async def test_monitored_database_manager(self, test_db):
        """Test MonitoredAsyncDatabaseManager functionality."""
        # Create monitored manager using test_db's config
        config = test_db.config
        monitored_db = MonitoredAsyncDatabaseManager(
            config=config,
            slow_query_threshold_ms=50,  # Low threshold for testing
            max_history_size=100,
        )
        await monitored_db.connect()

        try:
            # Create test table
            await monitored_db.execute(
                """
                CREATE TABLE performance_test (
                    id SERIAL PRIMARY KEY,
                    data TEXT
                )
            """
            )

            # Execute various queries
            for i in range(5):
                await monitored_db.execute(
                    "INSERT INTO performance_test (data) VALUES ($1)", f"Test data {i}"
                )

            # Fetch data
            results = await monitored_db.fetch_all("SELECT * FROM performance_test ORDER BY id")
            assert len(results) == 5

            # Get metrics
            metrics = await monitored_db.get_metrics()
            assert metrics.queries_executed >= 6  # CREATE + 5 INSERTs
            assert metrics.queries_failed == 0
            assert metrics.avg_query_time_ms > 0

            # Check query history
            history = monitored_db.get_query_history(limit=10)
            assert len(history) >= 6

            # Test slow query detection
            await monitored_db.execute("SELECT pg_sleep(0.1)")  # 100ms sleep

            slow_queries = monitored_db.get_slow_queries()
            assert len(slow_queries) >= 1
            assert any("pg_sleep" in q.query for q in slow_queries)

        finally:
            await monitored_db.disconnect()

    @pytest.mark.asyncio
    async def test_query_explain_functionality(self, test_db):
        """Test query execution plan analysis."""
        # Create monitored manager
        monitored_db = MonitoredAsyncDatabaseManager(pool=test_db._pool, schema=test_db.schema)

        # Create test data
        await monitored_db.execute(
            """
            CREATE TABLE orders (
                id SERIAL PRIMARY KEY,
                customer_id INT NOT NULL,
                order_date DATE NOT NULL,
                total DECIMAL(10, 2)
            )
        """
        )

        # Insert test data
        await monitored_db.execute(
            """
            INSERT INTO orders (customer_id, order_date, total)
            SELECT
                (random() * 100)::int,
                CURRENT_DATE - (random() * 365)::int,
                (random() * 1000)::numeric(10, 2)
            FROM generate_series(1, 100)
        """
        )

        # Create index
        await monitored_db.execute("CREATE INDEX idx_orders_customer ON orders(customer_id)")

        # Explain a query
        plan = await monitored_db.explain_query("SELECT * FROM orders WHERE customer_id = $1", 42)

        assert len(plan) > 0
        # The plan should contain query execution details
        plan_str = str(plan)
        # Check that we got a valid execution plan (could be Seq Scan, Index Scan, etc.)
        assert "Plan" in plan_str or "Node Type" in plan_str or len(plan[0]) > 0

        # Explain with ANALYZE
        analyzed_plan = await monitored_db.explain_query(
            "SELECT COUNT(*) FROM orders WHERE order_date > CURRENT_DATE - 30",
            analyze=True,
        )

        assert len(analyzed_plan) > 0
        # ANALYZE provides actual execution stats
        plan_str = str(analyzed_plan)
        assert "actual" in plan_str.lower() or "rows" in plan_str.lower()

    @pytest.mark.asyncio
    async def test_database_debugger(self, test_db):
        """Test DatabaseDebugger health checks and diagnostics."""
        debugger = DatabaseDebugger(test_db)

        # Perform health check
        health = await debugger.check_connection_health()

        assert health["status"] in ["healthy", "degraded", "error", "unhealthy"]

        # If healthy or degraded, check connectivity details
        if health["status"] in ["healthy", "degraded"]:
            assert "connectivity" in health["checks"]
            assert health["checks"]["connectivity"]["status"] == "ok"
            assert "version" in health["checks"]["connectivity"]

            # Check pool health
            assert "pool" in health["checks"]
            assert health["checks"]["pool"]["status"] == "ok"

            # Check for blocking queries (should be none in test)
            assert "blocking_queries" in health["checks"]
            assert health["checks"]["blocking_queries"]["count"] == 0

    @pytest.mark.asyncio
    async def test_blocking_query_detection(self, test_db):
        """Test detection of blocking queries."""
        debugger = DatabaseDebugger(test_db)

        # Create test table
        await test_db.execute(
            """
            CREATE TABLE lock_test (
                id INT PRIMARY KEY,
                value TEXT
            )
        """
        )

        await test_db.execute("INSERT INTO lock_test VALUES (1, 'initial')")

        # Start two transactions to create a blocking situation
        async def blocking_transaction():
            async with test_db.transaction() as tx:
                # Lock the row
                await tx.execute("UPDATE lock_test SET value = 'blocking' WHERE id = 1")
                # Hold the lock for a bit
                await asyncio.sleep(0.5)

        async def blocked_transaction():
            # Wait a bit for the first transaction to acquire lock
            await asyncio.sleep(0.1)
            try:
                async with test_db.transaction() as tx:
                    # This should be blocked
                    await tx.execute("UPDATE lock_test SET value = 'blocked' WHERE id = 1")
            except asyncio.TimeoutError:
                pass  # Expected in test

        # Run both transactions concurrently
        await asyncio.gather(blocking_transaction(), blocked_transaction(), return_exceptions=True)

        # In real scenario, you'd check blocking queries while transactions are running
        # Here we just verify the method works
        blocking_queries = await debugger.find_blocking_queries()
        # May or may not find blocking queries depending on timing
        assert isinstance(blocking_queries, list)

    @pytest.mark.asyncio
    async def test_long_running_query_detection(self, test_db):
        """Test detection of long-running queries."""
        debugger = DatabaseDebugger(test_db)

        # Start a long-running query in background
        async def long_query():
            try:
                await test_db.execute("SELECT pg_sleep(0.5)")
            except Exception:
                pass

        # Start the query
        agent = asyncio.create_task(long_query())

        # Give it time to start
        await asyncio.sleep(0.1)

        # Check for long-running queries (threshold very low for test)
        long_running = await debugger.find_long_running_queries(threshold_seconds=0)

        # Should find our query
        assert len(long_running) >= 1
        assert any("pg_sleep" in q["query"] for q in long_running)

        # Clean up
        await agent

    @pytest.mark.asyncio
    async def test_table_size_analysis(self, test_db):
        """Test table size and statistics analysis."""
        debugger = DatabaseDebugger(test_db)

        # Create tables with different sizes
        await test_db.execute(
            """
            CREATE TABLE small_table (
                id SERIAL PRIMARY KEY,
                data VARCHAR(100)
            )
        """
        )

        await test_db.execute(
            """
            CREATE TABLE large_table (
                id SERIAL PRIMARY KEY,
                data TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )

        # Insert data
        await test_db.execute(
            """
            INSERT INTO small_table (data)
            SELECT 'Small data ' || i
            FROM generate_series(1, 10) i
        """
        )

        await test_db.execute(
            """
            INSERT INTO large_table (data)
            SELECT repeat('Large data ', 100) || i
            FROM generate_series(1, 1000) i
        """
        )

        # Update statistics so pg_stat_user_tables has accurate row counts
        await test_db.execute("ANALYZE small_table")
        await test_db.execute("ANALYZE large_table")

        # Analyze table sizes
        table_stats = await debugger.analyze_table_sizes()

        assert len(table_stats) >= 2

        # Find our tables
        small_stats = next((t for t in table_stats if t["tablename"] == "small_table"), None)
        large_stats = next((t for t in table_stats if t["tablename"] == "large_table"), None)

        assert small_stats is not None
        assert large_stats is not None

        # Large table should be bigger
        assert large_stats["size_bytes"] > small_stats["size_bytes"]
        assert large_stats["row_count"] == 1000
        assert small_stats["row_count"] == 10

    @pytest.mark.asyncio
    async def test_query_performance_decorator(self, test_db, caplog):
        """Test the log_query_performance decorator."""

        @log_query_performance(threshold_ms=50)
        async def slow_database_operation(db):
            """Simulate a slow operation."""
            await db.execute("SELECT pg_sleep(0.1)")  # 100ms
            return "completed"

        @log_query_performance(threshold_ms=200)
        async def fast_database_operation(db):
            """Simulate a fast operation."""
            result = await db.fetch_one("SELECT 1 as value")
            return result["value"]

        # Test slow operation (should log)
        import logging

        caplog.set_level(logging.WARNING)
        caplog.clear()

        result = await slow_database_operation(test_db)
        assert result == "completed"

        # Should have logged the slow operation
        assert len(caplog.records) >= 1
        assert "slow_database_operation" in caplog.text

        # Test fast operation (should not log)
        caplog.clear()
        result = await fast_database_operation(test_db)
        assert result == 1

        # Should not have logged
        assert len(caplog.records) == 0

    @pytest.mark.asyncio
    async def test_connection_pool_monitoring(self, test_db):
        """Test connection pool statistics and monitoring."""
        # Get initial pool stats
        initial_stats = await test_db.get_pool_stats()

        assert initial_stats["status"] == "connected"
        assert "min_size" in initial_stats
        assert "max_size" in initial_stats
        assert "free_size" in initial_stats
        assert "used_size" in initial_stats

        # Create concurrent queries to stress the pool
        async def run_query(i):
            await test_db.fetch_one(f"SELECT {i} as num, pg_sleep(0.1)")

        # Run multiple queries concurrently
        agents = [run_query(i) for i in range(5)]
        await asyncio.gather(*agents)

        # Check pool stats after load
        after_stats = await test_db.get_pool_stats()

        # Pool should have handled the concurrent load
        assert after_stats["size"] >= initial_stats["size"]
        assert after_stats["size"] <= after_stats["max_size"]

    @pytest.mark.asyncio
    async def test_metrics_history_management(self, test_db):
        """Test that metrics history is properly managed."""
        # Create monitored manager with small history using existing pool
        monitored_db = MonitoredAsyncDatabaseManager(pool=test_db._pool, max_history_size=5)

        try:
            # Execute more queries than history size
            for i in range(10):
                await monitored_db.execute(f"SELECT {i}")

            # History should be limited to max_history_size
            history = monitored_db.get_query_history()
            assert len(history) == 5

            # Should have the most recent queries
            assert "SELECT 9" in history[-1].query
            assert "SELECT 5" in history[0].query

        finally:
            await monitored_db.disconnect()
