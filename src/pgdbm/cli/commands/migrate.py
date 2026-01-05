"""Migration management commands."""

import re
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import click

if TYPE_CHECKING:
    from ..config import EnvironmentConfig

from pgdbm import AsyncDatabaseManager, AsyncMigrationManager

from ..config import (
    get_env_config,
    get_env_config_from_env,
    get_module_config,
    resolve_module_order,
)
from ..utils import get_connection_config, run_async


@click.group()
def migrate() -> None:
    """Migration management commands."""
    pass


@migrate.command()
@click.option("--module", "-m", help="Apply migrations for specific module")
@click.option("--all", "apply_all", is_flag=True, help="Apply migrations for all modules")
@click.option("--dry-run", is_flag=True, help="Show what would be applied without applying")
@click.pass_context
def apply(ctx: click.Context, module: Optional[str], apply_all: bool, dry_run: bool) -> None:
    """Apply pending migrations."""
    config = ctx.obj.get("config")
    env = ctx.obj["env"]

    if not config:
        # Simple mode - look for migrations in current directory
        migrations_path = Path("migrations")
        if not migrations_path.exists():
            click.echo(
                "No migrations directory found. Create migrations/ or use --config", err=True
            )
            ctx.exit(1)

        env_config = get_env_config_from_env()
        if not env_config:
            click.echo(
                "Error: DATABASE_URL is required for simple mode (or provide --config).",
                err=True,
            )
            ctx.exit(1)

        _apply_simple_migrations(env_config, migrations_path, dry_run)
        return

    # Module mode
    if apply_all:
        modules = resolve_module_order(config)
        click.echo(f"Resolved module order: {' → '.join(modules)}")
    elif module:
        modules = [module]
    else:
        # Default to all modules if config exists
        modules = resolve_module_order(config)

    env_config = get_env_config(config, env)
    if not env_config:
        click.echo(f"Error: No configuration for environment '{env}'", err=True)
        ctx.exit(1)

    async def _apply() -> None:
        db_config = get_connection_config(env_config)
        db = AsyncDatabaseManager(db_config)
        await db.connect()

        try:
            total_applied = 0

            for module_name in modules:
                module_config = get_module_config(config, module_name)
                if not module_config:
                    click.echo(f"Warning: No configuration for module '{module_name}'", err=True)
                    continue

                migrations_path = Path(module_config.migrations_path)
                if not migrations_path.exists():
                    click.echo(
                        f"Warning: Migrations path not found for {module_name}: {migrations_path}"
                    )
                    continue

                click.echo(f"\nApplying migrations for module: {module_name}")

                if dry_run:
                    # Show what would be applied
                    # Note: schema must be set on db manager, not migration manager
                    manager = AsyncMigrationManager(
                        db,
                        str(migrations_path),
                        module_name=module_name,
                    )

                    pending = await manager.get_pending_migrations()
                    if pending:
                        click.echo(f"  Would apply {len(pending)} migration(s):")
                        for mig in pending:
                            click.echo(f"    - {mig}")
                    else:
                        click.echo("  No pending migrations")
                else:
                    # Actually apply
                    # Note: schema must be set on db manager, not migration manager
                    manager = AsyncMigrationManager(
                        db,
                        str(migrations_path),
                        module_name=module_name,
                    )

                    result = await manager.apply_pending_migrations()

                    if result["applied"]:
                        for migration in result["applied"]:
                            click.echo(
                                f"  ✓ {migration['filename']} ({migration['execution_time_ms']}ms)"
                            )
                        total_applied += len(result["applied"])
                    else:
                        click.echo("  No pending migrations")

            if not dry_run:
                click.echo(f"\n✓ Applied {total_applied} migration(s) total")

        finally:
            await db.disconnect()

    run_async(_apply())


def _apply_simple_migrations(
    env_config: "EnvironmentConfig", migrations_path: Path, dry_run: bool
) -> None:
    """Apply migrations in simple mode (no modules)."""

    async def _apply() -> None:
        db_config = get_connection_config(env_config)
        db = AsyncDatabaseManager(db_config)
        await db.connect()

        try:
            manager = AsyncMigrationManager(db, str(migrations_path))

            if dry_run:
                pending = await manager.get_pending_migrations()
                if pending:
                    click.echo(f"Would apply {len(pending)} migration(s):")
                    for mig in pending:
                        click.echo(f"  - {mig}")
                else:
                    click.echo("No pending migrations")
            else:
                result = await manager.apply_pending_migrations()

                if result["applied"]:
                    click.echo(f"Applied {len(result['applied'])} migration(s):")
                    for migration in result["applied"]:
                        click.echo(
                            f"  ✓ {migration['filename']} ({migration['execution_time_ms']}ms)"
                        )
                else:
                    click.echo("No pending migrations")
        finally:
            await db.disconnect()

    run_async(_apply())


@migrate.command()
@click.option("--module", "-m", help="Show status for specific module")
@click.option("--all-modules", is_flag=True, help="Show status for all modules")
@click.pass_context
def status(ctx: click.Context, module: Optional[str], all_modules: bool) -> None:
    """Show migration status."""
    config = ctx.obj.get("config")
    env = ctx.obj["env"]

    env_config = get_env_config(config, env)
    if not env_config and not config:
        env_config = get_env_config_from_env()
    if not env_config:
        if config:
            click.echo(f"Error: No configuration for environment '{env}'", err=True)
        else:
            click.echo(
                "Error: DATABASE_URL is required for simple mode (or provide --config).",
                err=True,
            )
        ctx.exit(1)

    if not config or (not module and not all_modules):
        # Simple mode
        _show_simple_status(env_config)
        return

    # Module mode
    if all_modules:
        modules = list(config.modules.keys())
    elif module:
        modules = [module]
    else:
        modules = list(config.modules.keys())

    async def _status() -> None:
        db_config = get_connection_config(env_config)
        db = AsyncDatabaseManager(db_config)
        await db.connect()

        try:
            for module_name in modules:
                module_config = get_module_config(config, module_name)
                if not module_config:
                    continue

                migrations_path = Path(module_config.migrations_path)
                if not migrations_path.exists():
                    click.echo(f"\nModule: {module_name}")
                    click.echo("  Status: Migrations path not found")
                    continue

                # Note: schema must be set on db manager, not migration manager
                manager = AsyncMigrationManager(
                    db,
                    str(migrations_path),
                    module_name=module_name,
                )

                applied = await manager.get_applied_migrations()
                pending = await manager.get_pending_migrations()

                # Display schema info
                schema_name = module_config.schema_name or (
                    env_config.schema_name if env_config else "public"
                )
                click.echo(f"\nModule: {module_name}")
                click.echo(f"  Schema: {schema_name}")
                click.echo(f"  Applied: {len(applied)}")
                click.echo(f"  Pending: {len(pending)}")

                if applied:
                    click.echo("  Last applied:")
                    # applied is a dict[str, Migration], get the last value
                    applied_list = list(applied.values())
                    last = applied_list[-1]
                    click.echo(f"    {last.filename} at {last.applied_at}")

                if pending:
                    click.echo("  Next to apply:")
                    click.echo(f"    {pending[0]}")

        finally:
            await db.disconnect()

    run_async(_status())


def _show_simple_status(env_config: "EnvironmentConfig") -> None:
    """Show migration status in simple mode."""
    migrations_path = Path("migrations")
    if not migrations_path.exists():
        click.echo("No migrations directory found")
        return

    async def _status() -> None:
        db_config = get_connection_config(env_config)
        db = AsyncDatabaseManager(db_config)
        await db.connect()

        try:
            manager = AsyncMigrationManager(db, str(migrations_path))

            applied = await manager.get_applied_migrations()
            pending = await manager.get_pending_migrations()

            click.echo(f"Applied: {len(applied)}")
            click.echo(f"Pending: {len(pending)}")

            if applied:
                click.echo("\nApplied migrations:")
                # applied is a dict[str, Migration], iterate over values
                for mig in applied.values():
                    click.echo(f"  ✓ {mig.filename} at {mig.applied_at}")

            if pending:
                click.echo("\nPending migrations:")
                for mig in pending:
                    click.echo(f"  - {mig}")

        finally:
            await db.disconnect()

    run_async(_status())


@migrate.command()
@click.argument("name")
@click.option("--module", "-m", help="Create migration for specific module")
@click.option("--sql", is_flag=True, help="Create SQL migration (default)")
@click.option("--path", type=click.Path(path_type=Path), help="Override migrations path")  # type: ignore[type-var]
@click.pass_context
def create(
    ctx: click.Context, name: str, module: Optional[str], sql: bool, path: Optional[Path]
) -> None:
    """Create a new migration file."""
    config = ctx.obj.get("config")

    # Determine migrations path
    if path:
        migrations_path = path
    elif module and config:
        module_config = get_module_config(config, module)
        if not module_config:
            click.echo(f"Error: No configuration for module '{module}'", err=True)
            ctx.exit(1)
        migrations_path = Path(module_config.migrations_path)
    else:
        migrations_path = Path("migrations")

    # Create directory if needed
    migrations_path.mkdir(parents=True, exist_ok=True)

    # Find next version number
    existing = list(migrations_path.glob("*.sql"))
    if existing:
        # Extract version numbers
        versions = []
        for f in existing:
            match = re.match(r"(\d+)", f.name)
            if match:
                versions.append(int(match.group(1)))
        next_version = max(versions) + 1 if versions else 1
    else:
        next_version = 1

    # Create filename
    filename = f"{next_version:03d}_{name}.sql"
    filepath = migrations_path / filename

    # Create template
    template = f"""-- Migration: {filename}
-- Created: {datetime.now().isoformat()}
-- Description: {name.replace('_', ' ').title()}

-- Add your migration SQL here
-- Use {{{{tables.tablename}}}} syntax for schema-aware table names

"""

    filepath.write_text(template)
    click.echo(f"✓ Created migration: {filepath}")

    if module and config:
        module_config = get_module_config(config, module)
        if module_config and module_config.schema_name:
            click.echo(f"  Schema: {module_config.schema_name}")
            click.echo("  Remember to use {{tables.}} syntax for table names")


@migrate.command()
@click.option("--module", "-m", required=True, help="Module to rollback")
@click.option("--version", "-v", required=True, help="Version to rollback to")
@click.option("--confirm", is_flag=True, help="Skip confirmation")
@click.pass_context
def rollback(ctx: click.Context, module: str, version: str, confirm: bool) -> None:
    """Rollback migrations to a specific version."""
    config = ctx.obj.get("config")
    env = ctx.obj["env"]

    if not config:
        click.echo("Rollback requires a configuration file with modules", err=True)
        ctx.exit(1)

    module_config = get_module_config(config, module)
    if not module_config:
        click.echo(f"Error: No configuration for module '{module}'", err=True)
        ctx.exit(1)

    env_config = get_env_config(config, env)
    if not env_config:
        click.echo(f"Error: No configuration for environment '{env}'", err=True)
        ctx.exit(1)

    if not confirm:
        click.confirm(
            f"⚠️  Rollback module '{module}' to version {version}? This may delete data!", abort=True
        )

    async def _rollback() -> None:
        db_config = get_connection_config(env_config)
        db = AsyncDatabaseManager(db_config)
        await db.connect()

        try:
            # Note: schema must be set on db manager, not migration manager
            manager = AsyncMigrationManager(
                db,
                str(Path(module_config.migrations_path)),
                module_name=module,
            )

            # Get applied migrations
            applied = await manager.get_applied_migrations()

            # Find migrations to rollback
            # applied is a dict[str, Migration], convert to list and reverse
            applied_list = list(applied.values())
            to_rollback = []
            for mig in reversed(applied_list):
                if mig.version > version:
                    to_rollback.append(mig)
                else:
                    break

            if not to_rollback:
                click.echo(f"No migrations to rollback (already at or before version {version})")
                return

            click.echo(f"Will rollback {len(to_rollback)} migration(s):")
            for mig in to_rollback:
                click.echo(f"  - {mig.filename}")

            # Note: Actual rollback would require down migrations
            # This is a simplified version
            click.echo("\nNote: Rollback requires down migrations which are not yet implemented")
            click.echo("You may need to manually reverse the changes")

        finally:
            await db.disconnect()

    run_async(_rollback())
