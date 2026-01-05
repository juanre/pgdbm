"""Configuration management for pgdbm CLI."""

import os
from pathlib import Path
from typing import Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # noqa: F401

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class ModuleConfig(BaseModel):
    """Configuration for a module."""

    model_config = ConfigDict(use_enum_values=True)

    migrations_path: str
    schema_name: Optional[str] = Field(None, alias="schema")
    mode: str = "dual"  # standalone | library | dual
    depends_on: list[str] = Field(default_factory=list)


class EnvironmentConfig(BaseModel):
    """Configuration for an environment."""

    model_config = ConfigDict(use_enum_values=True)

    url: Optional[str] = None
    connection_string: Optional[str] = None
    host: Optional[str] = None
    port: int = 5432
    database: Optional[str] = None
    user: Optional[str] = None
    password: Optional[str] = None
    schema_name: str = Field("public", alias="schema")
    ssl_enabled: bool = False
    ssl_mode: Optional[str] = None
    ssl_ca_file: Optional[str] = None
    ssl_cert_file: Optional[str] = None
    ssl_key_file: Optional[str] = None

    @field_validator("url", "connection_string")
    @classmethod
    def expand_env_vars(cls, v: Optional[str]) -> Optional[str]:
        """Expand environment variables in connection strings."""
        if v and v.startswith("${") and v.endswith("}"):
            env_var = v[2:-1]
            return os.environ.get(env_var)
        return v

    def get_connection_string(self) -> str:
        """Get the connection string for this environment."""
        if self.url:
            return self.url
        if self.connection_string:
            return self.connection_string

        # Build from components
        if not self.host or not self.database:
            raise ValueError("Must provide either url/connection_string or host+database")

        auth = ""
        if self.user:
            auth = self.user
            if self.password:
                auth += f":{self.password}"
            auth += "@"

        return f"postgresql://{auth}{self.host}:{self.port}/{self.database}"


class SharedPoolConfig(BaseModel):
    """Configuration for shared connection pool."""

    min_connections: int = 10
    max_connections: int = 100
    modules: list[str] = Field(default_factory=list)


class ProjectConfig(BaseModel):
    """Project configuration."""

    name: str
    default_env: str = "dev"


class DatabaseConfig(BaseModel):
    """Database configuration."""

    migrations_table: str = "schema_migrations"


class Config(BaseModel):
    """Complete configuration."""

    project: Optional[ProjectConfig] = None
    database: Optional[DatabaseConfig] = None
    environments: dict[str, EnvironmentConfig] = Field(default_factory=dict)
    modules: dict[str, ModuleConfig] = Field(default_factory=dict)
    shared_pool: Optional[SharedPoolConfig] = None


def load_config(config_path: Path, environment: Optional[str] = None) -> Config:
    """Load configuration from a TOML file.

    Args:
        config_path: Path to the configuration file
        environment: Override environment to use

    Returns:
        Loaded configuration

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValidationError: If config is invalid
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    try:
        config = Config(**data)
    except ValidationError as e:
        raise ValueError(f"Invalid configuration: {e}") from e

    # Set default environment if not specified
    if environment and config.project:
        config.project.default_env = environment

    return config


def get_env_config(config: Optional[Config], env: str) -> Optional[EnvironmentConfig]:
    """Get environment configuration.

    Args:
        config: Configuration object
        env: Environment name

    Returns:
        Environment configuration if found
    """
    if not config:
        return None

    return config.environments.get(env)


def get_env_config_from_env() -> Optional[EnvironmentConfig]:
    """Build environment configuration from DATABASE_URL for simple mode."""
    url = os.environ.get("DATABASE_URL")
    if not url:
        return None
    return EnvironmentConfig(url=url)  # type: ignore[call-arg]


def get_module_config(config: Optional[Config], module: str) -> Optional[ModuleConfig]:
    """Get module configuration.

    Args:
        config: Configuration object
        module: Module name

    Returns:
        Module configuration if found
    """
    if not config:
        return None

    return config.modules.get(module)


def resolve_module_order(config: Config) -> list[str]:
    """Resolve module dependency order.

    Args:
        config: Configuration object

    Returns:
        List of module names in dependency order

    Raises:
        ValueError: If circular dependencies detected
    """
    if not config.modules:
        return []

    # Build dependency graph
    deps: dict[str, list[str]] = {}
    for name, module in config.modules.items():
        deps[name] = module.depends_on

    # Topological sort
    result = []
    visited = set()
    temp_visited = set()

    def visit(node: str) -> None:
        if node in temp_visited:
            raise ValueError(f"Circular dependency detected involving {node}")
        if node in visited:
            return

        temp_visited.add(node)
        for dep in deps.get(node, []):
            if dep in deps:  # Only visit if dep is a known module
                visit(dep)
        temp_visited.remove(node)
        visited.add(node)
        result.append(node)

    for module_name in deps:
        if module_name not in visited:
            visit(module_name)

    return result


def create_default_config() -> Config:
    """Create a default configuration."""
    return Config(
        project=ProjectConfig(name="pgdbm_project"),
        database=DatabaseConfig(),
        environments={
            "dev": EnvironmentConfig(
                host="localhost",
                database="pgdbm_dev",
                user="postgres",
                schema="public",
            ),
            "test": EnvironmentConfig(
                host="localhost",
                database="pgdbm_test",
                user="postgres",
                schema="public",
            ),
        },
    )
