"""CLI for admin database operations."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path to allow imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.config import config
from app.db.admin import AdminDatabase
from pgdbm import AsyncDatabaseManager, DatabaseConfig


async def migrate_public():
    """Run public schema migrations."""
    print("Running public schema migrations...")

    # Create database config
    db_config = DatabaseConfig(
        connection_string=config.database_url,
        min_connections=config.admin_pool_min,
        max_connections=config.admin_pool_max,
    )

    # Create database manager
    db_manager = AsyncDatabaseManager(db_config)
    await db_manager.connect()

    try:
        # Create admin database instance
        admin_db = AdminDatabase(db_manager)

        # Run migrations
        await admin_db.migrate_public_schema()

        print("✓ Public schema migrations completed successfully")

    finally:
        await db_manager.disconnect()


async def create_tenant(slug: str, name: str, email: str, plan: str = "free"):
    """Create a new tenant."""
    print(f"Creating tenant: {slug}")

    # Create database config
    db_config = DatabaseConfig(
        connection_string=config.database_url,
        min_connections=config.admin_pool_min,
        max_connections=config.admin_pool_max,
    )

    # Create database manager
    db_manager = AsyncDatabaseManager(db_config)
    await db_manager.connect()

    try:
        # Create admin database instance
        admin_db = AdminDatabase(db_manager)

        # Import model after sys.path is set
        from app.models.tenant import TenantCreate

        # Create tenant
        tenant_data = TenantCreate(slug=slug, name=name, email=email, plan=plan)

        tenant = await admin_db.create_tenant(tenant_data)
        print(f"✓ Tenant created successfully: {tenant.id}")
        print(f"  Slug: {tenant.slug}")
        print(f"  API Key: {tenant.api_key}")

    finally:
        await db_manager.disconnect()


def print_usage():
    """Print usage information."""
    print("Usage: python -m app.db.admin <command> [args]")
    print("\nCommands:")
    print("  migrate_public              Run public schema migrations")
    print("  create_tenant <slug> <name> <email> [plan]  Create a new tenant")
    print("\nExamples:")
    print("  python -m app.db.admin migrate_public")
    print("  python -m app.db.admin create_tenant acme 'Acme Corp' admin@acme.com pro")


def main():
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    command = sys.argv[1]

    if command == "migrate_public":
        asyncio.run(migrate_public())
    elif command == "create_tenant":
        if len(sys.argv) < 5:
            print("Error: create_tenant requires slug, name, and email arguments")
            print_usage()
            sys.exit(1)

        slug = sys.argv[2]
        name = sys.argv[3]
        email = sys.argv[4]
        plan = sys.argv[5] if len(sys.argv) > 5 else "free"

        asyncio.run(create_tenant(slug, name, email, plan))
    else:
        print(f"Unknown command: {command}")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
