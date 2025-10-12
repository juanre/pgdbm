"""Development workflow commands."""

import asyncio
import signal
import sys
from pathlib import Path
from typing import Any, Optional

import click

from pgdbm import AsyncDatabaseManager, AsyncMigrationManager

from ..config import get_env_config, get_module_config, resolve_module_order
from ..utils import get_connection_config, run_async


@click.group()
def dev() -> None:
    """Development workflow commands."""
    pass


@dev.command()
@click.pass_context
def start(ctx: click.Context) -> None:
    """Start development environment."""
    config = ctx.obj.get("config")
    env = "dev"  # Always use dev for this command

    click.echo("Starting development environment...")

    # Create database if needed
    ctx.obj["env"] = env
    ctx.invoke(create_db, confirm=True)

    # Apply migrations
    if config and config.modules:
        ctx.invoke(apply_migrations, apply_all=True)
    else:
        # Simple mode
        migrations_path = Path("migrations")
        if migrations_path.exists():
            ctx.invoke(apply_migrations)

    # Show connection info
    env_config = get_env_config(config, env)
    if env_config:
        conn_str = env_config.get_connection_string()
        click.echo("\n✓ Development environment ready!")
        click.echo(f"  Connection: {conn_str}")

        if config and config.modules:
            click.echo(f"  Modules: {', '.join(config.modules.keys())}")


@dev.command()
@click.option("--interval", "-i", default=2, help="Check interval in seconds")
@click.pass_context
def watch(ctx: click.Context, interval: int) -> None:
    """Watch for migration changes and auto-apply."""
    config = ctx.obj.get("config")
    env = ctx.obj["env"]

    env_config = get_env_config(config, env)
    if not env_config:
        click.echo(f"Error: No configuration for environment '{env}'", err=True)
        ctx.exit(1)

    click.echo(f"Watching for migration changes (checking every {interval}s)...")
    click.echo("Press Ctrl+C to stop")

    def signal_handler(signum: int, frame: Any) -> None:
        click.echo("\n✓ Stopped watching")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    async def _watch() -> None:
        db_config = get_connection_config(env_config)
        db = AsyncDatabaseManager(db_config)
        await db.connect()

        try:
            while True:
                # Check each module
                if config and config.modules:
                    modules = resolve_module_order(config)
                    for module_name in modules:
                        module_config = get_module_config(config, module_name)
                        if not module_config:
                            continue

                        migrations_path = Path(module_config.migrations_path)
                        if not migrations_path.exists():
                            continue

                        # Note: schema must be set on db manager, not migration manager
                        manager = AsyncMigrationManager(
                            db,
                            str(migrations_path),
                            module_name=module_name,
                        )

                        pending = await manager.get_pending_migrations()

                        if pending:
                            click.echo(f"\nFound {len(pending)} new migration(s) in {module_name}")
                            result = await manager.apply_pending_migrations()

                            for migration in result["applied"]:
                                click.echo(f"  ✓ Applied {migration['filename']}")
                else:
                    # Simple mode
                    migrations_path = Path("migrations")
                    if migrations_path.exists():
                        manager = AsyncMigrationManager(db, str(migrations_path))
                        pending = await manager.get_pending_migrations()

                        if pending:
                            click.echo(f"\nFound {len(pending)} new migration(s)")
                            result = await manager.apply_pending_migrations()

                            for migration in result["applied"]:
                                click.echo(f"  ✓ Applied {migration['filename']}")

                await asyncio.sleep(interval)

        finally:
            await db.disconnect()

    run_async(_watch())


@dev.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation")
@click.pass_context
def reset(ctx: click.Context, confirm: bool) -> None:
    """Reset development environment to clean state."""
    env = "dev"  # Always use dev for this command
    ctx.obj["env"] = env

    if not confirm:
        click.confirm("⚠️  Reset development database? This will delete all data!", abort=True)

    # Reset database
    from .db import create, drop

    ctx.invoke(drop, confirm=True)
    ctx.invoke(create, confirm=True)

    # Re-apply migrations
    config = ctx.obj.get("config")
    if config and config.modules:
        from .migrate import apply

        ctx.invoke(apply, apply_all=True)
    else:
        migrations_path = Path("migrations")
        if migrations_path.exists():
            from .migrate import apply

            ctx.invoke(apply)

    click.echo("✓ Development environment reset complete")


@dev.command(name="export-schema")
@click.option(
    "--output", "-o", type=click.Path(path_type=Path), default="schema.sql", help="Output file"  # type: ignore[type-var]
)
@click.option("--schema", "-s", help="Specific schema to export")
@click.pass_context
def export_schema(ctx: click.Context, output: Path, schema: Optional[str]) -> None:
    """Export current database schema."""
    config = ctx.obj.get("config")
    env = ctx.obj["env"]

    env_config = get_env_config(config, env)
    if not env_config:
        click.echo(f"Error: No configuration for environment '{env}'", err=True)
        ctx.exit(1)

    async def _export() -> None:
        db_config = get_connection_config(env_config)
        db = AsyncDatabaseManager(db_config)
        await db.connect()

        try:
            # Get schema DDL
            if schema:
                schemas = [schema]
            else:
                # Get all non-system schemas
                result = await db.fetch_all(
                    """
                    SELECT schema_name
                    FROM information_schema.schemata
                    WHERE schema_name NOT IN (
                        'pg_catalog', 'information_schema', 'pg_toast',
                        'pg_temp_1', 'pg_toast_temp_1'
                    )
                    ORDER BY schema_name
                """
                )
                schemas = [r["schema_name"] for r in result]

            ddl_parts = []

            for schema_name in schemas:
                # Export schema
                if schema_name != "public":
                    ddl_parts.append(f"CREATE SCHEMA IF NOT EXISTS {schema_name};")

                # Export tables
                tables = await db.fetch_all(
                    """
                    SELECT
                        table_name,
                        pg_get_ddl('CREATE TABLE', (table_schema||'.'||table_name)::regclass) as ddl
                    FROM information_schema.tables
                    WHERE table_schema = $1
                    AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                """,
                    schema_name,
                )

                for table in tables:
                    ddl_parts.append(f"\n-- Table: {schema_name}.{table['table_name']}")
                    ddl_parts.append(table["ddl"] + ";")

                # Export indexes
                indexes = await db.fetch_all(
                    """
                    SELECT indexdef
                    FROM pg_indexes
                    WHERE schemaname = $1
                    ORDER BY indexname
                """,
                    schema_name,
                )

                if indexes:
                    ddl_parts.append(f"\n-- Indexes for schema {schema_name}")
                    for idx in indexes:
                        ddl_parts.append(idx["indexdef"] + ";")

            # Write to file
            schema_sql = "\n".join(ddl_parts)
            output.write_text(schema_sql)

            click.echo(f"✓ Exported schema to {output}")
            click.echo(f"  Schemas: {', '.join(schemas)}")

        except Exception as e:
            click.echo(f"Error exporting schema: {e}", err=True)
            raise
        finally:
            await db.disconnect()

    run_async(_export())


# Helper functions for internal use
def create_db(ctx: click.Context, confirm: bool = False) -> None:
    """Internal helper to create database."""
    from .db import create

    ctx.invoke(create, confirm=confirm)


def apply_migrations(ctx: click.Context, apply_all: bool = False) -> None:
    """Internal helper to apply migrations."""
    from .migrate import apply

    ctx.invoke(apply, apply_all=apply_all)
