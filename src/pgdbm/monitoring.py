# Copyright (c) 2025 Juan Reyero
# Licensed under the MIT License

# ABOUTME: Database monitoring and debugging tools for tracking query performance, connection metrics, and slow queries.
# ABOUTME: Provides MonitoredAsyncDatabaseManager, DatabaseDebugger, and performance metrics collection classes.

"""
Monitoring and debugging utilities for async database operations.
"""

import functools
import logging
import time
from datetime import datetime
from typing import Any, Callable, Optional, TypeVar, cast

from pydantic import BaseModel

from pgdbm.core import AsyncDatabaseManager

logger = logging.getLogger(__name__)

T = TypeVar("T")


class QueryMetrics(BaseModel):
    """Metrics for a single query execution."""

    query: str
    args: list[Any]
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    rows_affected: Optional[int] = None
    error: Optional[str] = None

    def complete(self, error: Optional[Exception] = None) -> None:
        """Mark query as complete."""
        self.end_time = datetime.now()
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000
        if error:
            self.error = str(error)


class ConnectionMetrics(BaseModel):
    """Metrics for database connections."""

    timestamp: datetime
    pool_size: int
    pool_free: int
    pool_used: int
    pool_min: int
    pool_max: int
    queries_executed: int
    queries_failed: int
    avg_query_time_ms: float
    slowest_query_ms: float

    @property
    def pool_utilization(self) -> float:
        """Calculate pool utilization percentage."""
        if self.pool_max == 0:
            return 0.0
        return (self.pool_used / self.pool_max) * 100


class MonitoredAsyncDatabaseManager(AsyncDatabaseManager):
    """
    Database manager with built-in monitoring and debugging capabilities.

    This wraps the standard AsyncDatabaseManager to add:
    - Query execution tracking
    - Performance metrics
    - Slow query logging
    - Connection pool monitoring
    """

    def __init__(
        self,
        config: Optional[Any] = None,
        pool: Optional[Any] = None,
        schema: Optional[str] = None,
        slow_query_threshold_ms: int = 1000,
        max_history_size: int = 1000,
        record_args: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(config=config, pool=pool, schema=schema)
        self._query_history: list[QueryMetrics] = []
        self._queries_executed = 0
        self._queries_failed = 0
        self._slow_query_threshold_ms = float(slow_query_threshold_ms)
        self._max_history_size = max_history_size
        self._record_args = record_args

    async def _track_query(
        self, func: Callable[..., Any], query: str, args: tuple, **kwargs: Any
    ) -> Any:
        """Track query execution with metrics."""
        if self._record_args:
            masked_args = self._mask_sensitive_args(args)
            args_list = list(masked_args)
        else:
            args_list = []

        metrics = QueryMetrics(query=query, args=args_list, start_time=datetime.now())

        try:
            result = await func(query, *args, **kwargs)
            metrics.complete()
            self._queries_executed += 1

            # Log slow queries
            if metrics.duration_ms and metrics.duration_ms > self._slow_query_threshold_ms:
                logger.warning(
                    f"Slow query detected ({metrics.duration_ms:.2f}ms): " f"{query[:100]}..."
                )

            return result

        except Exception as e:
            metrics.complete(error=e)
            self._queries_failed += 1
            raise

        finally:
            # Add to history (with size limit)
            self._query_history.append(metrics)
            if len(self._query_history) > self._max_history_size:
                self._query_history.pop(0)

    async def execute(self, query: str, *args: Any, **kwargs: Any) -> str:
        """Execute a query with tracking."""
        result = await self._track_query(super().execute, query, args, **kwargs)
        return cast(str, result)

    async def fetch_one(self, query: str, *args: Any, **kwargs: Any) -> Optional[dict[str, Any]]:
        """Fetch one row with tracking."""
        result = await self._track_query(super().fetch_one, query, args, **kwargs)
        return cast(Optional[dict[str, Any]], result)

    async def fetch_all(self, query: str, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        """Fetch all rows with tracking."""
        result = await self._track_query(super().fetch_all, query, args, **kwargs)
        return cast(list[dict[str, Any]], result)

    async def get_metrics(self) -> ConnectionMetrics:
        """Get current connection and query metrics."""
        pool_stats = await self.get_pool_stats()

        # Calculate query statistics
        if self._query_history:
            query_times = [q.duration_ms for q in self._query_history if q.duration_ms is not None]
            avg_query_time = sum(query_times) / len(query_times) if query_times else 0
            slowest_query = max(query_times) if query_times else 0
        else:
            avg_query_time = 0
            slowest_query = 0

        return ConnectionMetrics(
            timestamp=datetime.now(),
            pool_size=pool_stats.get("size", 0),
            pool_free=pool_stats.get("free_size", 0),
            pool_used=pool_stats.get("used_size", 0),
            pool_min=pool_stats.get("min_size", 0),
            pool_max=pool_stats.get("max_size", 0),
            queries_executed=self._queries_executed,
            queries_failed=self._queries_failed,
            avg_query_time_ms=avg_query_time,
            slowest_query_ms=slowest_query,
        )

    def get_query_history(
        self, limit: Optional[int] = None, include_errors: bool = True
    ) -> list[QueryMetrics]:
        """Get recent query history."""
        history = self._query_history

        if not include_errors:
            history = [q for q in history if q.error is None]

        if limit:
            history = history[-limit:]

        return history

    def get_slow_queries(self, threshold_ms: Optional[float] = None) -> list[QueryMetrics]:
        """Get queries that exceeded the threshold."""
        threshold = threshold_ms or self._slow_query_threshold_ms

        return [q for q in self._query_history if q.duration_ms and q.duration_ms > threshold]

    async def explain_query(
        self, query: str, *args: Any, analyze: bool = False
    ) -> list[dict[str, Any]]:
        """
        Get query execution plan using EXPLAIN.

        Args:
            query: SQL query to explain
            args: Query parameters
            analyze: If True, actually run the query (EXPLAIN ANALYZE)

        Returns:
            Query execution plan
        """
        explain_prefix = "EXPLAIN (FORMAT JSON"
        if analyze:
            explain_prefix += ", ANALYZE, BUFFERS"
        explain_prefix += ") "

        explained_query = explain_prefix + self._prepare_query(query)

        result = await self.fetch_one(explained_query, *args)
        if result and "QUERY PLAN" in result:
            return cast(list[dict[str, Any]], result["QUERY PLAN"])
        return []


class DatabaseDebugger:
    """Utilities for debugging database issues."""

    def __init__(self, db_manager: AsyncDatabaseManager):
        self.db = db_manager

    async def check_connection_health(self) -> dict[str, Any]:
        """Health check of database connections."""
        health: dict[str, Any] = {
            "status": "unknown",
            "timestamp": datetime.now().isoformat(),
            "checks": {},
        }

        try:
            # Check basic connectivity
            start = time.time()
            version = await self.db.fetch_value("SELECT version()")
            health["checks"]["connectivity"] = {
                "status": "ok",
                "response_time_ms": (time.time() - start) * 1000,
                "version": version,
            }

            # Check pool health
            pool_stats = await self.db.get_pool_stats()
            health["checks"]["pool"] = {"status": "ok", "stats": pool_stats}

            # Check for blocking queries
            blocking = await self.find_blocking_queries()
            health["checks"]["blocking_queries"] = {
                "status": "ok" if not blocking else "warning",
                "count": len(blocking),
                "queries": blocking[:5],  # Limit to 5
            }

            # Check for long-running queries
            long_running = await self.find_long_running_queries(60)  # 60 seconds
            health["checks"]["long_running_queries"] = {
                "status": "ok" if not long_running else "warning",
                "count": len(long_running),
                "queries": long_running[:5],
            }

            # Overall status
            if all(check.get("status") == "ok" for check in health["checks"].values()):
                health["status"] = "healthy"
            elif any(check.get("status") == "error" for check in health["checks"].values()):
                health["status"] = "unhealthy"
            else:
                health["status"] = "degraded"

        except Exception as e:
            health["status"] = "error"
            health["error"] = str(e)

        return health

    async def find_blocking_queries(self) -> list[dict[str, Any]]:
        """Find queries that are blocking other queries."""
        result: list[dict[str, Any]] = await self.db.fetch_all(
            """
            SELECT
                blocked_locks.pid AS blocked_pid,
                blocked_activity.usename AS blocked_user,
                blocking_locks.pid AS blocking_pid,
                blocking_activity.usename AS blocking_user,
                blocked_activity.query AS blocked_query,
                blocking_activity.query AS blocking_query,
                blocked_activity.state AS blocked_state,
                blocking_activity.state AS blocking_state
            FROM pg_catalog.pg_locks blocked_locks
            JOIN pg_catalog.pg_stat_activity blocked_activity
                ON blocked_activity.pid = blocked_locks.pid
            JOIN pg_catalog.pg_locks blocking_locks
                ON blocking_locks.locktype = blocked_locks.locktype
                AND blocking_locks.DATABASE IS NOT DISTINCT FROM blocked_locks.DATABASE
                AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation
                AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page
                AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple
                AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid
                AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid
                AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid
                AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid
                AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid
                AND blocking_locks.pid != blocked_locks.pid
            JOIN pg_catalog.pg_stat_activity blocking_activity
                ON blocking_activity.pid = blocking_locks.pid
            WHERE NOT blocked_locks.GRANTED
        """
        )
        return result

    async def find_long_running_queries(self, threshold_seconds: int = 300) -> list[dict[str, Any]]:
        """Find queries running longer than threshold."""
        result: list[dict[str, Any]] = await self.db.fetch_all(
            """
            SELECT
                pid,
                usename,
                datname,
                state,
                query,
                query_start,
                NOW() - query_start AS duration,
                wait_event_type,
                wait_event
            FROM pg_stat_activity
            WHERE state != 'idle'
            AND query NOT LIKE '%pg_stat_activity%'
            AND NOW() - query_start > make_interval(secs => $1)
            ORDER BY query_start
        """,
            threshold_seconds,
        )
        return result

    async def analyze_table_sizes(self) -> list[dict[str, Any]]:
        """Get table sizes and statistics."""
        if self.db.schema:
            result: list[dict[str, Any]] = await self.db.fetch_all(
                """
                SELECT
                    schemaname,
                    relname AS tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||relname)) AS size,
                    pg_total_relation_size(schemaname||'.'||relname) AS size_bytes,
                    n_live_tup AS row_count,
                    n_dead_tup AS dead_rows,
                    last_vacuum,
                    last_autovacuum,
                    last_analyze,
                    last_autoanalyze
                FROM pg_stat_user_tables
                WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                AND schemaname = $1
                ORDER BY pg_total_relation_size(schemaname||'.'||relname) DESC
                """,
                self.db.schema,
            )
        else:
            result = await self.db.fetch_all(
                """
                SELECT
                    schemaname,
                    relname AS tablename,
                    pg_size_pretty(pg_total_relation_size(schemaname||'.'||relname)) AS size,
                    pg_total_relation_size(schemaname||'.'||relname) AS size_bytes,
                    n_live_tup AS row_count,
                    n_dead_tup AS dead_rows,
                    last_vacuum,
                    last_autovacuum,
                    last_analyze,
                    last_autoanalyze
                FROM pg_stat_user_tables
                WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
                ORDER BY pg_total_relation_size(schemaname||'.'||relname) DESC
                """
            )
        return result


def log_query_performance(
    threshold_ms: float = 100, log_args: bool = False
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """
    Decorator to log slow queries.

    Usage:
        @log_query_performance(threshold_ms=500)
        async def my_query_function(db, user_id):
            return await db.fetch_one("SELECT * FROM users WHERE id = $1", user_id)
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.time()

            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.time() - start) * 1000

                if duration_ms > threshold_ms:
                    msg = f"Slow function {func.__name__} took {duration_ms:.2f}ms"
                    if log_args:
                        msg += f" (args: {args}, kwargs: {kwargs})"
                    logger.warning(msg)

                return result

            except Exception as e:
                duration_ms = (time.time() - start) * 1000
                logger.error(f"Function {func.__name__} failed after {duration_ms:.2f}ms: {e}")
                raise

        return wrapper

    return decorator
