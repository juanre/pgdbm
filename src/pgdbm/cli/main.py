"""Main CLI entry point for pgdbm."""

import sys
from pathlib import Path
from typing import Optional

import click

from pgdbm import __version__

from .commands import db, dev, generate, migrate, schema
from .config import load_config


@click.group()
@click.version_option(version=__version__, prog_name="pgdbm")
@click.option(
    "--config",
    "-c",
    type=click.Path(path_type=Path),  # type: ignore[type-var]
    default=None,
    help="Path to configuration file",
    envvar="PGDBM_CONFIG",
)
@click.option(
    "--env",
    "-e",
    type=str,
    default="dev",
    help="Environment to use",
    envvar="PGDBM_ENV",
)
@click.pass_context
def cli(ctx: click.Context, config: Optional[Path], env: str) -> None:
    """pgdbm - PostgreSQL Database Manager CLI.

    Manage PostgreSQL databases, migrations, and schemas with support for
    dual-mode libraries and multi-module applications.
    """
    ctx.ensure_object(dict)

    # Try to load config if it exists
    if not config:
        config = Path("pgdbm.toml")

    if config.exists():
        try:
            ctx.obj["config"] = load_config(config, env)
            ctx.obj["config_path"] = config
        except Exception as e:
            click.echo(f"Warning: Could not load config from {config}: {e}", err=True)
            ctx.obj["config"] = None
    else:
        ctx.obj["config"] = None

    ctx.obj["env"] = env


# Add command groups
cli.add_command(db.db)
cli.add_command(migrate.migrate)
cli.add_command(schema.schema)
cli.add_command(dev.dev)
cli.add_command(generate.generate)


def main() -> None:
    """Main entry point for the CLI."""
    try:
        cli()
    except Exception as e:
        click.echo(f"Error: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
