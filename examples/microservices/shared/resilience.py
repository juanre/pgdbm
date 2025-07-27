"""Resilience patterns for microservices."""

import asyncio
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Callable, Optional, TypeVar

import httpx

from .database import SharedDatabaseManager

T = TypeVar("T")


class CircuitBreakerError(Exception):
    """Raised when circuit breaker is open."""

    pass


class CircuitBreaker:
    """Circuit breaker pattern implementation."""

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = 5,
        recovery_timeout: int = 60,
        expected_exception: type = Exception,
    ):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self._db = None

    async def _get_db(self):
        """Get database connection."""
        if not self._db:
            shared = await SharedDatabaseManager.get_instance()
            self._db = shared.get_manager()
        return self._db

    async def _get_state(self) -> dict[str, Any]:
        """Get circuit breaker state from database."""
        db = await self._get_db()
        result = await db.fetch_one(
            "SELECT * FROM circuit_breakers WHERE service_name = $1", self.service_name
        )

        if not result:
            # Initialize state
            await db.execute(
                """
                INSERT INTO circuit_breakers (service_name, state)
                VALUES ($1, 'closed')
                ON CONFLICT (service_name) DO NOTHING
            """,
                self.service_name,
            )
            return {"state": "closed", "failure_count": 0}

        return dict(result)

    async def _update_state(self, state: str, failure_count: int = 0) -> None:
        """Update circuit breaker state."""
        db = await self._get_db()

        next_retry = None
        if state == "open":
            next_retry = datetime.utcnow() + timedelta(seconds=self.recovery_timeout)

        await db.execute(
            """
            UPDATE circuit_breakers
            SET state = $2,
                failure_count = $3,
                last_failure_time = CASE WHEN $3 > 0 THEN NOW() ELSE last_failure_time END,
                next_retry_time = $4,
                updated_at = NOW()
            WHERE service_name = $1
        """,
            self.service_name,
            state,
            failure_count,
            next_retry,
        )

    async def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """Execute function with circuit breaker protection."""
        state = await self._get_state()

        # Check if circuit is open
        if state["state"] == "open":
            if state.get("next_retry_time") and datetime.utcnow() >= state["next_retry_time"]:
                # Try half-open state
                await self._update_state("half-open")
            else:
                raise CircuitBreakerError(f"Circuit breaker is open for {self.service_name}")

        try:
            # Execute the function
            result = await func(*args, **kwargs)

            # Success - reset if needed
            if state["state"] == "half-open":
                await self._update_state("closed", 0)
            elif state["failure_count"] > 0:
                await self._update_state("closed", 0)

            return result

        except self.expected_exception as e:
            # Failure - increment counter
            failure_count = state["failure_count"] + 1

            if failure_count >= self.failure_threshold:
                await self._update_state("open", failure_count)
                raise CircuitBreakerError(f"Circuit breaker opened for {self.service_name}") from e
            else:
                await self._update_state(state["state"], failure_count)
                raise


def circuit_breaker(
    service_name: str,
    failure_threshold: int = 5,
    recovery_timeout: int = 60,
    expected_exception: type = Exception,
):
    """Decorator for circuit breaker pattern."""
    cb = CircuitBreaker(service_name, failure_threshold, recovery_timeout, expected_exception)

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await cb.call(func, *args, **kwargs)

        return wrapper

    return decorator


class RetryPolicy:
    """Retry policy for failed operations."""

    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_backoff: bool = True,
        jitter: bool = True,
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_backoff = exponential_backoff
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for retry attempt."""
        if self.exponential_backoff:
            delay = min(self.initial_delay * (2**attempt), self.max_delay)
        else:
            delay = self.initial_delay

        if self.jitter:
            import random

            delay *= 0.5 + random.random()

        return delay


async def retry_async(
    func: Callable[..., T], *args, policy: Optional[RetryPolicy] = None, **kwargs
) -> T:
    """Retry an async function with the given policy."""
    if policy is None:
        policy = RetryPolicy()

    last_exception = None

    for attempt in range(policy.max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            last_exception = e

            if attempt < policy.max_retries:
                delay = policy.get_delay(attempt)
                await asyncio.sleep(delay)
            else:
                raise

    raise last_exception


def with_retry(policy: Optional[RetryPolicy] = None):
    """Decorator for retry pattern."""

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await retry_async(func, *args, policy=policy, **kwargs)

        return wrapper

    return decorator


class ServiceClient:
    """Base HTTP client with resilience patterns."""

    def __init__(self, service_name: str, base_url: Optional[str] = None):
        self.service_name = service_name
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)
        self.circuit_breaker = CircuitBreaker(
            service_name,
            failure_threshold=5,
            recovery_timeout=60,
            expected_exception=httpx.HTTPError,
        )
        self.retry_policy = RetryPolicy(max_retries=3)

    async def discover_service(self) -> str:
        """Discover service URL if not provided."""
        if self.base_url:
            return self.base_url

        from .database import discover_service

        url = await discover_service(self.service_name)
        if not url:
            raise ValueError(f"Service '{self.service_name}' not found in registry")

        return url

    async def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        """Make HTTP request with circuit breaker and retry."""
        base_url = await self.discover_service()
        url = f"{base_url}{path}"

        async def make_request():
            response = await self.client.request(method, url, **kwargs)
            response.raise_for_status()
            return response

        # Apply circuit breaker
        return await self.circuit_breaker.call(retry_async, make_request, policy=self.retry_policy)

    async def get(self, path: str, **kwargs) -> httpx.Response:
        """GET request."""
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs) -> httpx.Response:
        """POST request."""
        return await self.request("POST", path, **kwargs)

    async def put(self, path: str, **kwargs) -> httpx.Response:
        """PUT request."""
        return await self.request("PUT", path, **kwargs)

    async def delete(self, path: str, **kwargs) -> httpx.Response:
        """DELETE request."""
        return await self.request("DELETE", path, **kwargs)

    async def close(self):
        """Close HTTP client."""
        await self.client.aclose()
