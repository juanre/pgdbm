"""Application configuration."""

import os
import sys
from typing import Optional

from pydantic import BaseModel, Field


class Config(BaseModel):
    """Application configuration."""

    # Environment
    app_env: str = Field(default="development", description="Application environment")

    # Database
    database_url: Optional[str] = Field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL", "postgresql://postgres:postgres@localhost/saas_app"
        ),
        description="PostgreSQL connection URL",
    )

    # Connection pools
    tenant_pool_min: int = Field(default=5, ge=1)
    tenant_pool_max: int = Field(default=20, ge=1)
    admin_pool_min: int = Field(default=2, ge=1)
    admin_pool_max: int = Field(default=10, ge=1)

    # API Settings
    api_key_length: int = Field(default=32, ge=16, description="Length of generated API keys")

    # Tenant limits
    max_projects_per_tenant: int = Field(default=100, ge=1)
    max_users_per_tenant: int = Field(default=50, ge=1)

    # Features
    enable_monitoring: bool = Field(default=False)
    enable_billing: bool = Field(default=True)

    def validate_config(self) -> None:
        """Validate configuration."""
        if not self.database_url:
            raise ValueError("DATABASE_URL must be set")

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

# Validate on import (skip for tests and CLI commands)
skip_validation = (
    any("test" in arg for arg in sys.argv)
    or
    # Skip validation for admin CLI commands
    (len(sys.argv) > 1 and sys.argv[0].endswith("__main__.py"))
    or
    # Skip if running as module with commands
    ("app.db.admin" in sys.argv[0])
)

if not skip_validation:
    try:
        config.validate_config()
    except ValueError as e:
        # Only print warning in development, fail in production
        if config.app_env == "development":
            print(f"Warning: {e}")
            print("Using default database URL: postgresql://postgres:postgres@localhost/saas_app")
        else:
            raise
