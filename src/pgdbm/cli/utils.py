"""Utility functions for the CLI."""

import asyncio
from collections.abc import Coroutine
from concurrent.futures import Future
from threading import Thread
from typing import Any, Optional, TypeVar

from pgdbm import DatabaseConfig

from .config import EnvironmentConfig

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Run an async function in a sync context.

    Args:
        coro: Coroutine to run

    Returns:
        Result of the coroutine
    """
    try:
        loop = asyncio.get_running_loop()
        # If a loop is running in this thread, we can't call run_until_complete().
        # Run the coroutine in a fresh event loop on a helper thread instead.
        if loop.is_running():
            future: Future[T] = Future()

            def _runner() -> None:
                try:
                    future.set_result(asyncio.run(coro))
                except BaseException as exc:  # pragma: no cover - defensive
                    future.set_exception(exc)

            thread = Thread(target=_runner, name="pgdbm-cli-run-async")
            thread.start()
            thread.join()
            return future.result()

        return loop.run_until_complete(coro)
    except RuntimeError:
        # No running loop, create one
        return asyncio.run(coro)


def get_connection_config(env_config: Optional[EnvironmentConfig]) -> DatabaseConfig:
    """Convert environment config to database config.

    Args:
        env_config: Environment configuration

    Returns:
        Database configuration for AsyncDatabaseManager

    Raises:
        ValueError: If env_config is None
    """
    if env_config is None:
        raise ValueError("Environment configuration is required")

    conn_str = env_config.get_connection_string()

    config_dict: dict[str, Any] = {
        "connection_string": conn_str,
        "schema": env_config.schema_name,
    }

    # Add SSL configuration if present
    if env_config.ssl_enabled:
        config_dict["ssl_enabled"] = env_config.ssl_enabled
        if env_config.ssl_mode:
            config_dict["ssl_mode"] = env_config.ssl_mode
        if env_config.ssl_ca_file:
            config_dict["ssl_ca_file"] = env_config.ssl_ca_file
        if env_config.ssl_cert_file:
            config_dict["ssl_cert_file"] = env_config.ssl_cert_file
        if env_config.ssl_key_file:
            config_dict["ssl_key_file"] = env_config.ssl_key_file

    return DatabaseConfig(**config_dict)


def format_time(ms: float) -> str:
    """Format milliseconds as a human-readable time string.

    Args:
        ms: Time in milliseconds

    Returns:
        Formatted time string
    """
    if ms < 1000:
        return f"{ms:.0f}ms"
    elif ms < 60000:
        return f"{ms / 1000:.1f}s"
    else:
        return f"{ms / 60000:.1f}m"


def format_size(bytes: int) -> str:
    """Format bytes as a human-readable size string.

    Args:
        bytes: Size in bytes

    Returns:
        Formatted size string
    """
    size_float = float(bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_float < 1024:
            return f"{size_float:.1f} {unit}"
        size_float /= 1024
    return f"{size_float:.1f} PB"
