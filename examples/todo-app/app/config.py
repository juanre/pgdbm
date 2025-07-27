"""Application configuration."""

import os
import sys
from typing import Optional

from pydantic import BaseModel, Field


class Config(BaseModel):
    """Application configuration with validation."""

    # Environment
    app_env: str = Field(default="development", description="Application environment")

    # Database
    database_url: Optional[str] = Field(
        default_factory=lambda: os.environ.get("DATABASE_URL"),
        description="PostgreSQL connection URL",
    )
    database_schema: str = Field(default="todo_app", description="Database schema name")

    # Connection pool
    db_min_connections: int = Field(default=10, ge=1, description="Minimum database connections")
    db_max_connections: int = Field(default=20, ge=1, description="Maximum database connections")

    # Features
    enable_monitoring: bool = Field(default=False, description="Enable database query monitoring")

    # API
    api_prefix: str = Field(default="/api", description="API route prefix")

    def validate_config(self) -> None:
        """Validate configuration."""
        if not self.database_url:
            raise ValueError("DATABASE_URL must be set")

        if self.db_min_connections > self.db_max_connections:
            raise ValueError("db_min_connections cannot exceed db_max_connections")

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.app_env == "production"

    @property
    def is_testing(self) -> bool:
        """Check if running tests."""
        return self.app_env == "testing"


# Global config instance
config = Config()

# Validate on import (skip for verification scripts)
if not any("verify" in arg or "test_" in arg for arg in sys.argv):
    try:
        config.validate_config()
    except ValueError:
        if config.is_testing:
            # Allow missing DATABASE_URL in tests
            pass
        else:
            raise
