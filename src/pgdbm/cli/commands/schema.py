"""Schema management commands."""

from typing import Optional

import click

from pgdbm import AsyncDatabaseManager

from ..config import get_env_config, get_module_config
from ..utils import get_connection_config, run_async


@click.group()
def schema() -> None:
    """Schema management commands."""
    pass


@schema.command(name="list")
@click.pass_context
def list_schemas(ctx: click.Context) -> None:
    """List all schemas and their modules."""
    config = ctx.obj.get("config")
    env = ctx.obj["env"]

    env_config = get_env_config(config, env)
    if not env_config:
        click.echo(f"Error: No configuration for environment '{env}'", err=True)
        ctx.exit(1)

    async def _list() -> None:
        db_config = get_connection_config(env_config)
        db = AsyncDatabaseManager(db_config)
        await db.connect()

        try:
            # Get all schemas
            schemas = await db.fetch_all(
                """
                SELECT
                    schema_name,
                    schema_owner
                FROM information_schema.schemata
                WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast', 'pg_temp_1', 'pg_toast_temp_1')
                ORDER BY schema_name
            """
            )

            click.echo("Database Schemas:")
            for schema in schemas:
                # Count tables
                table_count = await db.fetch_one(
                    """
                    SELECT COUNT(*) as count
                    FROM information_schema.tables
                    WHERE table_schema = $1
                    AND table_type = 'BASE TABLE'
                """,
                    schema["schema_name"],
                )
                assert table_count is not None  # COUNT(*) always returns a result

                # Check if it's a module schema
                module_name = None
                if config and config.modules:
                    for name, mod_config in config.modules.items():
                        if mod_config.schema_name == schema["schema_name"]:
                            module_name = name
                            break

                info = f"  {schema['schema_name']} ({table_count['count']} tables)"
                if module_name:
                    info += f" - module: {module_name}"
                click.echo(info)

            # Show module configuration if available
            if config and config.modules:
                click.echo("\nConfigured Modules:")
                for name, mod_config in config.modules.items():
                    schema_name = mod_config.schema_name or (
                        env_config.schema_name if env_config else "public"
                    )
                    click.echo(f"  {name} → {schema_name}")
                    if mod_config.depends_on:
                        click.echo(f"    depends on: {', '.join(mod_config.depends_on)}")

        finally:
            await db.disconnect()

    run_async(_list())


@schema.command()
@click.option("--module", "-m", required=True, help="Module name")
@click.option("--name", "-n", help="Schema name (defaults to module name)")
@click.pass_context
def create(ctx: click.Context, module: str, name: Optional[str]) -> None:
    """Create schema for a module."""
    config = ctx.obj.get("config")
    env = ctx.obj["env"]

    env_config = get_env_config(config, env)
    if not env_config:
        click.echo(f"Error: No configuration for environment '{env}'", err=True)
        ctx.exit(1)

    schema_name = name or module

    async def _create() -> None:
        db_config = get_connection_config(env_config)
        db = AsyncDatabaseManager(db_config)
        await db.connect()

        try:
            # Check if schema exists
            exists = await db.fetch_one(
                """
                SELECT 1 FROM information_schema.schemata
                WHERE schema_name = $1
            """,
                schema_name,
            )

            if exists:
                click.echo(f"Schema '{schema_name}' already exists")
                return

            # Create schema
            await db.execute(f'CREATE SCHEMA "{schema_name}"')
            click.echo(f"✓ Created schema '{schema_name}'")

            # Update config recommendation
            if config and module in config.modules:
                click.echo("\nUpdate your pgdbm.toml to use this schema:")
                click.echo(f"  [modules.{module}]")
                click.echo(f'  schema = "{schema_name}"')

        finally:
            await db.disconnect()

    run_async(_create())


@schema.command()
@click.option("--module", "-m", required=True, help="Module to show dependencies for")
@click.pass_context
def deps(ctx: click.Context, module: str) -> None:
    """Show schema dependencies for a module."""
    config = ctx.obj.get("config")

    if not config:
        click.echo("Dependencies require a configuration file", err=True)
        ctx.exit(1)

    module_config = get_module_config(config, module)
    if not module_config:
        click.echo(f"Module '{module}' not found in configuration", err=True)
        ctx.exit(1)

    # Build dependency tree
    def show_deps(name: str, level: int = 0) -> None:
        indent = "  " * level
        mod = config.modules.get(name)
        if not mod:
            return

        schema = mod.schema_name or "public"
        click.echo(f"{indent}{name} → {schema}")

        for dep in mod.depends_on:
            show_deps(dep, level + 1)

    click.echo(f"Dependencies for {module}:")
    show_deps(module)

    # Show reverse dependencies
    reverse_deps = []
    for name, mod in config.modules.items():
        if module in mod.depends_on:
            reverse_deps.append(name)

    if reverse_deps:
        click.echo(f"\nModules that depend on {module}:")
        for dep in reverse_deps:
            click.echo(f"  - {dep}")


@schema.command()
@click.option("--dry-run", is_flag=True, help="Show what would be cleaned without doing it")
@click.option("--confirm", is_flag=True, help="Skip confirmation")
@click.pass_context
def clean(ctx: click.Context, dry_run: bool, confirm: bool) -> None:
    """Clean unused schemas."""
    config = ctx.obj.get("config")
    env = ctx.obj["env"]

    env_config = get_env_config(config, env)
    if not env_config:
        click.echo(f"Error: No configuration for environment '{env}'", err=True)
        ctx.exit(1)

    async def _clean() -> None:
        db_config = get_connection_config(env_config)
        db = AsyncDatabaseManager(db_config)
        await db.connect()

        try:
            # Get all schemas
            schemas = await db.fetch_all(
                """
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name NOT IN (
                    'pg_catalog', 'information_schema', 'pg_toast',
                    'pg_temp_1', 'pg_toast_temp_1', 'public'
                )
            """
            )

            # Find configured schemas
            configured_schemas = set()
            if config and config.modules:
                for mod in config.modules.values():
                    if mod.schema_name:
                        configured_schemas.add(mod.schema_name)

            # Find unused schemas
            unused = []
            for schema in schemas:
                name = schema["schema_name"]
                if name not in configured_schemas:
                    # Check if empty
                    table_count = await db.fetch_one(
                        """
                        SELECT COUNT(*) as count
                        FROM information_schema.tables
                        WHERE table_schema = $1
                        AND table_type = 'BASE TABLE'
                    """,
                        name,
                    )
                    assert table_count is not None  # COUNT(*) always returns a result

                    if table_count["count"] == 0:
                        unused.append(name)

            if not unused:
                click.echo("No unused schemas found")
                return

            click.echo(f"Found {len(unused)} unused schema(s):")
            for name in unused:
                click.echo(f"  - {name}")

            if dry_run:
                click.echo("\nDry run - no changes made")
                return

            if not confirm:
                click.confirm("Clean these schemas?", abort=True)

            # Drop unused schemas
            for name in unused:
                await db.execute(f'DROP SCHEMA "{name}" CASCADE')
                click.echo(f"  ✓ Dropped {name}")

            click.echo(f"\n✓ Cleaned {len(unused)} schema(s)")

        finally:
            await db.disconnect()

    run_async(_clean())
