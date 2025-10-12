"""Configuration management using environment variables."""

from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings from environment variables."""

    # Application
    app_name: str = "Production pgdbm App"
    app_env: str = Field(
        default="development", description="Environment: development, staging, production"
    )
    app_debug: bool = Field(default=False, description="Debug mode")
    app_log_level: str = Field(default="info", description="Logging level")

    # Database
    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/production_app",
        description="PostgreSQL connection string",
    )
    database_min_connections: int = Field(default=10, description="Minimum pool connections")
    database_max_connections: int = Field(default=50, description="Maximum pool connections")
    database_command_timeout: float = Field(default=30.0, description="Query timeout in seconds")
    database_ssl_enabled: bool = Field(default=False, description="Enable SSL for database")

    # Security
    secret_key: str = Field(
        default="change-me-in-production", description="Secret key for security"
    )
    cors_origins: list[str] = Field(default=["*"], description="Allowed CORS origins")

    # Monitoring
    slow_query_threshold_ms: int = Field(default=1000, description="Slow query threshold")
    enable_metrics: bool = Field(default=True, description="Enable Prometheus metrics")

    # Testing
    test_database_url: Optional[str] = Field(default=None, description="Test database URL")

    class Config:
        env_file = ".env"
        case_sensitive = False

    @property
    def is_production(self) -> bool:
        """Check if running in production."""
        return self.app_env == "production"

    @property
    def is_testing(self) -> bool:
        """Check if running tests."""
        return self.app_env == "testing"


# Global settings instance
settings = Settings()
