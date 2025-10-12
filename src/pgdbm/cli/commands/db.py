"""Database management commands."""

import asyncpg
import click

from pgdbm import AsyncDatabaseManager

from ..config import get_env_config
from ..utils import get_connection_config, run_async


@click.group()
def db() -> None:
    """Database management commands."""
    pass


@db.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def create(ctx: click.Context, confirm: bool) -> None:
    """Create the database."""
    config = ctx.obj.get("config")
    env = ctx.obj["env"]

    env_config = get_env_config(config, env)
    if not env_config:
        click.echo(f"Error: No configuration found for environment '{env}'", err=True)
        ctx.exit(1)

    conn_str = env_config.get_connection_string()

    # Parse database name from connection string
    import urllib.parse

    parsed = urllib.parse.urlparse(conn_str)
    db_name = parsed.path.lstrip("/")

    if not db_name:
        click.echo("Error: Could not determine database name from connection string", err=True)
        ctx.exit(1)

    if not confirm:
        click.confirm(f"Create database '{db_name}' in environment '{env}'?", abort=True)

    async def _create() -> None:
        # Connect to postgres database to create the target database
        admin_conn_str = conn_str.replace(f"/{db_name}", "/postgres")

        try:
            conn = await asyncpg.connect(admin_conn_str)
            try:
                # Check if database exists
                exists = await conn.fetchval(
                    "SELECT 1 FROM pg_database WHERE datname = $1", db_name
                )

                if exists:
                    click.echo(f"Database '{db_name}' already exists")
                    return

                # Create database
                await conn.execute(f'CREATE DATABASE "{db_name}"')
                click.echo(f"✓ Created database '{db_name}'")

            finally:
                await conn.close()

        except asyncpg.InvalidCatalogNameError:
            click.echo(f"✓ Database '{db_name}' already exists")
        except Exception as e:
            click.echo(f"Error creating database: {e}", err=True)
            raise

    run_async(_create())


@db.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def drop(ctx: click.Context, confirm: bool) -> None:
    """Drop the database."""
    config = ctx.obj.get("config")
    env = ctx.obj["env"]

    env_config = get_env_config(config, env)
    if not env_config:
        click.echo(f"Error: No configuration found for environment '{env}'", err=True)
        ctx.exit(1)

    conn_str = env_config.get_connection_string()

    # Parse database name from connection string
    import urllib.parse

    parsed = urllib.parse.urlparse(conn_str)
    db_name = parsed.path.lstrip("/")

    if not db_name:
        click.echo("Error: Could not determine database name from connection string", err=True)
        ctx.exit(1)

    if not confirm:
        click.confirm(
            f"⚠️  Drop database '{db_name}' in environment '{env}'? This cannot be undone!",
            abort=True,
        )

    async def _drop() -> None:
        # Connect to postgres database to drop the target database
        admin_conn_str = conn_str.replace(f"/{db_name}", "/postgres")

        try:
            conn = await asyncpg.connect(admin_conn_str)
            try:
                # Terminate existing connections
                await conn.execute(
                    """
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = $1
                    AND pid <> pg_backend_pid()
                """,
                    db_name,
                )

                # Drop database
                await conn.execute(f'DROP DATABASE IF EXISTS "{db_name}"')
                click.echo(f"✓ Dropped database '{db_name}'")

            finally:
                await conn.close()

        except Exception as e:
            click.echo(f"Error dropping database: {e}", err=True)
            raise

    run_async(_drop())


@db.command()
@click.option("--confirm", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def reset(ctx: click.Context, confirm: bool) -> None:
    """Reset the database (drop and recreate)."""
    if not confirm:
        env = ctx.obj["env"]
        click.confirm(
            f"⚠️  Reset database in environment '{env}'? This will delete all data!", abort=True
        )

    # Call drop and create commands
    ctx.invoke(drop, confirm=True)
    ctx.invoke(create, confirm=True)

    click.echo("✓ Database reset complete")


@db.command(name="test-connection")
@click.pass_context
def test_connection(ctx: click.Context) -> None:
    """Test database connection."""
    config = ctx.obj.get("config")
    env = ctx.obj["env"]

    env_config = get_env_config(config, env)
    if not env_config:
        click.echo(f"Error: No configuration found for environment '{env}'", err=True)
        ctx.exit(1)

    conn_str = env_config.get_connection_string()

    async def _test() -> None:
        try:
            # Try to connect
            conn = await asyncpg.connect(conn_str, timeout=5)
            try:
                # Get version
                version = await conn.fetchval("SELECT version()")
                click.echo("✓ Connection successful!")
                click.echo(f"  PostgreSQL: {version.split(',')[0]}")

                # Get database info
                db_name = await conn.fetchval("SELECT current_database()")
                db_size = await conn.fetchval(
                    "SELECT pg_size_pretty(pg_database_size(current_database()))"
                )
                click.echo(f"  Database: {db_name}")
                click.echo(f"  Size: {db_size}")

            finally:
                await conn.close()

        except asyncpg.InvalidPasswordError:
            click.echo("✗ Connection failed: Invalid password", err=True)
            ctx.exit(1)
        except asyncpg.InvalidCatalogNameError as e:
            click.echo(f"✗ Connection failed: Database does not exist - {e}", err=True)
            ctx.exit(1)
        except Exception as e:
            click.echo(f"✗ Connection failed: {e}", err=True)
            ctx.exit(1)

    run_async(_test())


@db.command()
@click.pass_context
def info(ctx: click.Context) -> None:
    """Show database information."""
    config = ctx.obj.get("config")
    env = ctx.obj["env"]

    env_config = get_env_config(config, env)
    if not env_config:
        click.echo(f"Error: No configuration found for environment '{env}'", err=True)
        ctx.exit(1)

    db_config = get_connection_config(env_config)

    async def _info() -> None:
        db = AsyncDatabaseManager(db_config)
        await db.connect()

        try:
            # Get database info
            info = await db.fetch_one(
                """
                SELECT
                    current_database() as database,
                    pg_size_pretty(pg_database_size(current_database())) as size,
                    version() as version
            """
            )
            assert info is not None  # Query always returns a result

            click.echo(f"Database: {info['database']}")
            click.echo(f"Size: {info['size']}")
            click.echo(f"Version: {info['version'].split(',')[0]}")
            click.echo()

            # Get schemas
            schemas = await db.fetch_all(
                """
                SELECT schema_name
                FROM information_schema.schemata
                WHERE schema_name NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                ORDER BY schema_name
            """
            )

            click.echo("Schemas:")
            for schema in schemas:
                # Count tables in schema
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

                click.echo(f"  - {schema['schema_name']} ({table_count['count']} tables)")

            click.echo()

            # Get connection pool info
            pool_info = await db.get_pool_stats()
            click.echo("Connection Pool:")
            click.echo(f"  Size: {pool_info['size']}")
            click.echo(f"  Free: {pool_info['free_size']}")
            click.echo(f"  Min: {pool_info['min_size']}")
            click.echo(f"  Max: {pool_info['max_size']}")

        finally:
            await db.disconnect()

    run_async(_info())
