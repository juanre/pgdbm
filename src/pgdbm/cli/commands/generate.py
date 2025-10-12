"""Code generation commands for dual-mode libraries."""

from pathlib import Path
from typing import Optional

import click


@click.group()
def generate() -> None:
    """Code generation commands."""
    pass


@generate.command()
@click.argument("name")
@click.option(
    "--dual-mode", is_flag=True, default=True, help="Generate dual-mode library (default)"
)
@click.option("--path", "-p", type=click.Path(path_type=Path), help="Output path")  # type: ignore[type-var]
@click.option("--with-api", is_flag=True, help="Include FastAPI boilerplate")
@click.pass_context
def library(
    ctx: click.Context, name: str, dual_mode: bool, path: Optional[Path], with_api: bool
) -> None:
    """Generate a dual-mode library scaffold."""

    # Determine output path
    if path:
        output_path = path / name
    else:
        output_path = Path.cwd() / name

    # Create directory structure
    output_path.mkdir(parents=True, exist_ok=True)
    src_path = output_path / "src" / name
    src_path.mkdir(parents=True, exist_ok=True)
    migrations_path = output_path / "migrations"
    migrations_path.mkdir(exist_ok=True)
    tests_path = output_path / "tests"
    tests_path.mkdir(exist_ok=True)

    # Generate __init__.py
    init_content = f'''"""{ name.replace("_", " ").title()} - A dual-mode pgdbm library."""

from .core import {name.title().replace("_", "")}Service
from .database import Database

__version__ = "0.1.0"
__all__ = ["{name.title().replace("_", "")}Service", "Database"]
'''
    (src_path / "__init__.py").write_text(init_content)

    # Generate database.py
    database_content = f'''"""Database management for {name}."""

from pathlib import Path
from typing import Optional

from pgdbm import AsyncDatabaseManager, AsyncMigrationManager, DatabaseConfig


class Database:
    """Database manager supporting dual-mode operation.

    Can work standalone (creates own connection) or integrated
    (uses external connection pool).
    """

    def __init__(
        self,
        connection_string: Optional[str] = None,
        db_manager: Optional[AsyncDatabaseManager] = None,
        schema: Optional[str] = None,
    ):
        """Initialize database in standalone or library mode.

        Args:
            connection_string: Connection string for standalone mode
            db_manager: External database manager for library mode
            schema: Schema name (defaults to '{name}')
        """
        if not connection_string and not db_manager:
            raise ValueError("Either connection_string or db_manager required")

        self._external_db = db_manager is not None
        self.db = db_manager
        self._connection_string = connection_string
        self.schema = schema or "{name}"

    async def initialize(self) -> None:
        """Initialize database and run migrations."""
        # Create connection if standalone
        if not self._external_db:
            config = DatabaseConfig(
                connection_string=self._connection_string,
                schema=self.schema
            )
            self.db = AsyncDatabaseManager(config)
            await self.db.connect()

        # Always run migrations
        await self._run_migrations()

    async def _run_migrations(self) -> None:
        """Run pending migrations."""
        migrations_path = Path(__file__).parent.parent.parent / "migrations"

        migrations = AsyncMigrationManager(
            self.db,
            str(migrations_path),
            module_name=f"{name}_{{self.schema}}"
        )

        result = await migrations.apply_pending_migrations()
        if result.get("applied"):
            print(f"Applied {{len(result['applied'])}} migrations")

    async def cleanup(self) -> None:
        """Clean up database resources."""
        if not self._external_db and self.db:
            await self.db.disconnect()
'''
    (src_path / "database.py").write_text(database_content)

    # Generate core.py
    core_content = f'''"""Core service implementation for {name}."""

from typing import Any, Dict, List, Optional

from .database import Database


class {name.title().replace("_", "")}Service:
    """Main service class for {name}."""

    def __init__(self, database: Database):
        """Initialize service with database.

        Args:
            database: Database instance (standalone or integrated)
        """
        self.db = database

    async def initialize(self) -> None:
        """Initialize the service."""
        await self.db.initialize()

    async def cleanup(self) -> None:
        """Clean up service resources."""
        await self.db.cleanup()

    # Add your service methods here
    async def example_method(self) -> Dict[str, Any]:
        """Example service method."""
        # Use self.db.db for database operations
        result = await self.db.db.fetch("SELECT 1 as value")
        return {{"result": result}}
'''
    (src_path / "core.py").write_text(core_content)

    # Generate FastAPI app if requested
    if with_api:
        main_content = f'''"""FastAPI application for {name}."""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from pgdbm import AsyncDatabaseManager

from .core import {name.title().replace("_", "")}Service
from .database import Database


def create_app(
    db_manager: Optional[AsyncDatabaseManager] = None,
    run_migrations: bool = True,
    schema: Optional[str] = None,
    config: Optional[dict] = None
) -> FastAPI:
    """Create service app supporting both standalone and library modes.

    Args:
        db_manager: External database (library mode) or None (standalone)
        run_migrations: Whether to apply migrations on startup
        schema: Override schema name
        config: Override configuration

    Returns:
        Configured FastAPI application
    """

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Determine mode
        if db_manager:
            # Library mode: use provided database
            database = Database(db_manager=db_manager, schema=schema or "{name}")
        else:
            # Standalone mode: create own connection
            import os
            conn_str = os.environ.get("DATABASE_URL", "postgresql://localhost/{name}")
            database = Database(connection_string=conn_str, schema=schema or "{name}")

        # Initialize service
        service = {name.title().replace("_", "")}Service(database)
        await service.initialize()

        # Store in app state
        app.state.service = service
        app.state.external_db = db_manager is not None

        try:
            yield
        finally:
            await service.cleanup()

    # Create app
    app = FastAPI(
        title="{name.replace("_", " ").title()}",
        lifespan=lifespan,
    )

    # Add routes
    @app.get("/")
    async def root():
        return {{"service": "{name}", "status": "running"}}

    @app.get("/health")
    async def health():
        return {{"status": "healthy"}}

    # Add your API routes here

    return app


# Default app for standalone mode
app = create_app()
'''
        (src_path / "main.py").write_text(main_content)

        # Generate CLI
        cli_content = f'''"""CLI for {name}."""

import asyncio
import click

from .core import {name.title().replace("_", "")}Service
from .database import Database


@click.group()
def cli():
    """{name.replace("_", " ").title()} CLI"""
    pass


@cli.command()
@click.option("--host", default="0.0.0.0", help="Host to bind to")
@click.option("--port", default=8000, help="Port to bind to")
def serve(host: str, port: int):
    """Run service in standalone mode."""
    import uvicorn
    from .main import app

    uvicorn.run(app, host=host, port=port)


@cli.command()
@click.option("--connection", "-c", envvar="DATABASE_URL", help="Database connection string")
def migrate(connection: str):
    """Run migrations."""
    async def _migrate():
        db = Database(connection_string=connection)
        await db.initialize()
        await db.cleanup()

    asyncio.run(_migrate())


if __name__ == "__main__":
    cli()
'''
        (src_path / "cli.py").write_text(cli_content)

    # Generate initial migration
    migration_content = f"""-- Initial migration for {name}
-- Created with pgdbm generate library

CREATE TABLE IF NOT EXISTS {{{{tables.items}}}} (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_items_name ON {{{{tables.items}}}}(name);
"""
    (migrations_path / "001_initial.sql").write_text(migration_content)

    # Generate test file
    test_content = f'''"""Tests for {name}."""

import pytest
import pytest_asyncio
from pgdbm.fixtures.conftest import test_db_factory

from {name} import {name.title().replace("_", "")}Service, Database


@pytest_asyncio.fixture(params=["standalone", "library"])
async def service(request, test_db_factory):
    """Test service in both modes."""
    mode = request.param

    if mode == "standalone":
        # Test standalone mode
        db = Database(connection_string="postgresql://localhost/test_{name}")
        service = {name.title().replace("_", "")}Service(db)
    else:
        # Test library mode with external db
        external_db = await test_db_factory.create_db(suffix="{name}", schema="test")
        db = Database(db_manager=external_db)
        service = {name.title().replace("_", "")}Service(db)

    await service.initialize()

    try:
        yield service, mode
    finally:
        await service.cleanup()


async def test_service_modes(service):
    """Test service works in both modes."""
    svc, mode = service

    # Test basic functionality
    result = await svc.example_method()
    assert result is not None

    # Both modes should work identically
    assert "result" in result
'''
    (tests_path / f"test_{name}.py").write_text(test_content)

    # Generate README
    readme_content = f"""# {name.replace("_", " ").title()}

A dual-mode pgdbm library that can run standalone or as part of a larger application.

## Installation

```bash
pip install -e .
```

## Usage

### Standalone Mode

Run as a standalone service:

```python
from {name} import {name.title().replace("_", "")}Service, Database

# Create standalone database
db = Database(connection_string="postgresql://localhost/{name}")
service = {name.title().replace("_", "")}Service(db)
await service.initialize()

# Use the service
result = await service.example_method()
```

### Library Mode

Integrate with an existing application:

```python
from pgdbm import AsyncDatabaseManager
from {name} import {name.title().replace("_", "")}Service, Database

# Use external database connection
external_db = AsyncDatabaseManager(config)
await external_db.connect()

# Create service with shared connection
db = Database(db_manager=external_db, schema="{name}")
service = {name.title().replace("_", "")}Service(db)
await service.initialize()
```

{"### FastAPI Integration" if with_api else ""}

{f'''```python
from {name}.main import create_app

# Standalone mode
app = create_app()

# Library mode with shared database
app = create_app(db_manager=shared_db, schema="custom_schema")
```''' if with_api else ""}

## Development

```bash
# Run migrations
pgdbm migrate apply --module {name}

# Run tests
pytest tests/
```

## License

MIT
"""
    (output_path / "README.md").write_text(readme_content)

    # Generate pyproject.toml
    pyproject_content = f"""[project]
name = "{name}"
version = "0.1.0"
description = "A dual-mode pgdbm library"
requires-python = ">=3.9"
dependencies = [
    "pgdbm>=0.1.0",
    {"'fastapi>=0.100.0'," if with_api else ""}
    {"'uvicorn>=0.20.0'," if with_api else ""}
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
]
"""
    (output_path / "pyproject.toml").write_text(pyproject_content)

    click.echo(f"✓ Generated dual-mode library scaffold at {output_path}")
    click.echo(f"  Mode: {'Dual-mode' if dual_mode else 'Standard'}")
    if with_api:
        click.echo("  ✓ FastAPI integration included")
    click.echo("\nNext steps:")
    click.echo(f"  1. cd {output_path}")
    click.echo("  2. pip install -e .")
    click.echo("  3. pgdbm migrate apply")
    click.echo("  4. python -m src.{name}.cli serve  # If FastAPI included")


@generate.command()
@click.pass_context
def tests(ctx: click.Context) -> None:
    """Generate test fixtures for dual-mode testing."""

    test_file = Path("tests") / "test_dual_mode.py"
    test_file.parent.mkdir(exist_ok=True)

    content = '''"""Test fixtures for dual-mode library testing."""

import pytest
import pytest_asyncio
from pgdbm.fixtures.conftest import test_db_factory


@pytest_asyncio.fixture(params=["standalone", "library"])
async def dual_mode_db(request, test_db_factory):
    """Fixture that tests both standalone and library modes."""
    mode = request.param

    if mode == "standalone":
        # Create standalone database
        from your_service import Database
        db = Database(connection_string="postgresql://localhost/test_db")
        await db.initialize()
        yield db, mode
        await db.cleanup()
    else:
        # Use external database
        from your_service import Database
        external_db = await test_db_factory.create_db(suffix="test", schema="test")
        db = Database(db_manager=external_db)
        await db.initialize()
        yield db, mode
        # No cleanup needed - external db handles it


async def test_both_modes_work(dual_mode_db):
    """Test that service works in both modes."""
    db, mode = dual_mode_db

    # Both modes should work identically
    result = await db.db.fetch("SELECT 1 as value")
    assert result[0]["value"] == 1

    # Mode-specific assertions if needed
    if mode == "standalone":
        assert db._external_db is False
    else:
        assert db._external_db is True
'''

    test_file.write_text(content)
    click.echo(f"✓ Generated test fixtures at {test_file}")


@generate.command()
@click.option("--name", "-n", default="pgdbm_project", help="Project name")
@click.pass_context
def config(ctx: click.Context, name: str) -> None:
    """Generate a pgdbm.toml configuration file."""

    config_path = Path("pgdbm.toml")

    if config_path.exists():
        click.confirm(f"{config_path} already exists. Overwrite?", abort=True)

    content = f"""# pgdbm configuration file
# Generated with pgdbm generate config

[project]
name = "{name}"
default_env = "dev"

[database]
migrations_table = "schema_migrations"

# Environment configurations
[environments.dev]
host = "localhost"
port = 5432
database = "{name}_dev"
user = "postgres"
# password = "secret"  # Can also use ${{DB_PASSWORD}} for env var
schema = "public"

[environments.test]
host = "localhost"
port = 5432
database = "{name}_test"
user = "postgres"
schema = "test"

[environments.prod]
# Use environment variable for production
url = "${{DATABASE_URL}}"
schema = "production"
ssl_enabled = true
ssl_mode = "require"

# Module configurations (if using multi-module setup)
# [modules.users]
# migrations_path = "src/users/migrations"
# schema = "users"
# mode = "dual"  # standalone | library | dual
# depends_on = []

# [modules.billing]
# migrations_path = "src/billing/migrations"
# schema = "billing"
# mode = "library"
# depends_on = ["users"]

# Shared connection pool configuration (for integrated mode)
# [shared_pool]
# min_connections = 10
# max_connections = 100
# modules = ["users", "billing"]
"""

    config_path.write_text(content)
    click.echo(f"✓ Generated configuration at {config_path}")
    click.echo("\nNext steps:")
    click.echo("  1. Edit pgdbm.toml with your database settings")
    click.echo("  2. Run: pgdbm db create")
    click.echo("  3. Run: pgdbm migrate apply")
