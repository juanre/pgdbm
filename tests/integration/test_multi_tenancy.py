# Copyright (c) 2025 Juan Reyero
# Licensed under the MIT License

"""
Integration tests for schema-based multi-tenancy features.

These tests demonstrate how to use pgdbm for multi-tenant applications.
"""

import pytest

from pgdbm import AsyncDatabaseManager, DatabaseConfig, SchemaManager


class TestSchemaIsolation:
    """Test schema-based multi-tenancy features."""

    @pytest.mark.asyncio
    async def test_schema_creation_and_isolation(self, test_db):
        """Test creating and using isolated schemas."""
        # Create schemas for different tenants
        await test_db.execute('CREATE SCHEMA IF NOT EXISTS "tenant_a"')
        await test_db.execute('CREATE SCHEMA IF NOT EXISTS "tenant_b"')

        # Create managers for each tenant
        tenant_a_db = AsyncDatabaseManager(pool=test_db._pool, schema="tenant_a")
        tenant_b_db = AsyncDatabaseManager(pool=test_db._pool, schema="tenant_b")

        # Create same table structure in both schemas
        for tenant_db in [tenant_a_db, tenant_b_db]:
            await tenant_db.execute(
                """
                CREATE TABLE {{tables.customers}} (
                    id SERIAL PRIMARY KEY,
                    name VARCHAR(255) NOT NULL,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    subscription_tier VARCHAR(50)
                )
            """
            )

        # Insert different data in each schema
        await tenant_a_db.execute(
            "INSERT INTO {{tables.customers}} (name, email, subscription_tier) VALUES ($1, $2, $3)",
            "Acme Corp",
            "contact@acme.com",
            "enterprise",
        )

        await tenant_b_db.execute(
            "INSERT INTO {{tables.customers}} (name, email, subscription_tier) VALUES ($1, $2, $3)",
            "TechStart Inc",
            "hello@techstart.com",
            "startup",
        )

        # Verify data isolation
        tenant_a_customers = await tenant_a_db.fetch_all("SELECT * FROM {{tables.customers}}")
        tenant_b_customers = await tenant_b_db.fetch_all("SELECT * FROM {{tables.customers}}")

        assert len(tenant_a_customers) == 1
        assert tenant_a_customers[0]["name"] == "Acme Corp"

        assert len(tenant_b_customers) == 1
        assert tenant_b_customers[0]["name"] == "TechStart Inc"

        # Verify tables exist in correct schemas
        assert await tenant_a_db.table_exists("customers")
        assert await tenant_b_db.table_exists("customers")

    @pytest.mark.asyncio
    async def test_schema_placeholder_replacement(self, test_db_with_schema):
        """Test schema placeholder functionality."""
        # test_db_with_schema has schema="test_schema"

        # Create table using placeholder
        await test_db_with_schema.execute(
            """
            CREATE TABLE {{tables.products}} (
                id SERIAL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                price DECIMAL(10, 2)
            )
        """
        )

        # Insert using placeholder
        await test_db_with_schema.execute(
            "INSERT INTO {{tables.products}} (name, price) VALUES ($1, $2)",
            "Widget",
            19.99,
        )

        # Query using placeholder
        products = await test_db_with_schema.fetch_all(
            "SELECT * FROM {{tables.products}} WHERE price < $1", 50.0
        )

        assert len(products) == 1
        assert products[0]["name"] == "Widget"

        # Verify actual table location
        schema_check = await test_db_with_schema.fetch_one(
            """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_name = 'products'
        """
        )

        assert schema_check["table_schema"] == "test_schema"

    @pytest.mark.asyncio
    async def test_copy_records_respects_schema(self, test_db_with_schema):
        """Ensure COPY honors the manager schema in shared-pool mode."""
        await test_db_with_schema.execute(
            """
            CREATE TABLE {{tables.events}} (
                id SERIAL PRIMARY KEY,
                event_type VARCHAR(50) NOT NULL
            )
        """
        )

        events = [("page_view",), ("click",), ("signup",)]
        rows_inserted = await test_db_with_schema.copy_records_to_table(
            "events", records=events, columns=["event_type"]
        )

        assert rows_inserted == len(events)
        count = await test_db_with_schema.fetch_value("SELECT COUNT(*) FROM {{tables.events}}")
        assert count == len(events)

    @pytest.mark.asyncio
    async def test_cross_schema_queries(self, test_db):
        """Test queries across multiple schemas."""
        # Create main schema and shared schema
        await test_db.execute('CREATE SCHEMA IF NOT EXISTS "main"')
        await test_db.execute('CREATE SCHEMA IF NOT EXISTS "shared"')

        # Create shared reference data
        await test_db.execute(
            """
            CREATE TABLE shared.countries (
                id SERIAL PRIMARY KEY,
                code VARCHAR(2) UNIQUE NOT NULL,
                name VARCHAR(100) NOT NULL
            )
        """
        )

        await test_db.execute(
            """
            INSERT INTO shared.countries (code, name) VALUES
            ('US', 'United States'),
            ('UK', 'United Kingdom'),
            ('CA', 'Canada')
        """
        )

        # Create tenant-specific manager
        tenant_db = AsyncDatabaseManager(pool=test_db._pool, schema="main")

        # Create tenant table with foreign key to shared schema
        await tenant_db.execute(
            """
            CREATE TABLE {{tables.addresses}} (
                id SERIAL PRIMARY KEY,
                street VARCHAR(255),
                city VARCHAR(100),
                country_code VARCHAR(2) REFERENCES shared.countries(code)
            )
        """
        )

        # Insert address
        await tenant_db.execute(
            """
            INSERT INTO {{tables.addresses}} (street, city, country_code)
            VALUES ($1, $2, $3)
            """,
            "123 Main St",
            "New York",
            "US",
        )

        # Join across schemas
        result = await tenant_db.fetch_one(
            """
            SELECT
                a.street,
                a.city,
                c.name as country_name
            FROM {{tables.addresses}} a
            JOIN shared.countries c ON a.country_code = c.code
            WHERE a.id = 1
        """
        )

        assert result["street"] == "123 Main St"
        assert result["country_name"] == "United States"

    @pytest.mark.asyncio
    async def test_schema_manager(self, test_db):
        """Test SchemaManager utility class."""
        # Create a schema-specific database manager
        tenant_config = DatabaseConfig(
            host="localhost",
            database=test_db.config.database,
            user=test_db.config.user,
            password=test_db.config.password,
            schema="managed_tenant",  # Use the alias
        )

        tenant_db = AsyncDatabaseManager(config=tenant_config)
        await tenant_db.connect()

        # Use SchemaManager
        schema_mgr = SchemaManager(tenant_db)

        # Ensure schema exists
        await schema_mgr.ensure_schema_exists()

        # Verify schema was created
        schema_exists = await tenant_db.fetch_value(
            """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.schemata
                WHERE schema_name = $1
            )
        """,
            "managed_tenant",
        )

        assert schema_exists is True

        # Test table name qualification
        qualified_name = schema_mgr.qualify_table_name("users")
        assert qualified_name == "managed_tenant.users"

        await tenant_db.disconnect()

    @pytest.mark.asyncio
    async def test_shared_pool_multi_tenant(self, test_db):
        """Test using shared connection pool for multiple tenants."""
        # Get the pool from test_db
        shared_pool = test_db._pool

        # Create multiple tenant managers sharing the same pool
        tenants = {}
        for tenant_id in ["alpha", "beta", "gamma"]:
            # Create schema
            await test_db.execute(f'CREATE SCHEMA IF NOT EXISTS "{tenant_id}"')

            # Create manager
            tenants[tenant_id] = AsyncDatabaseManager(pool=shared_pool, schema=tenant_id)

        # Create tables and insert data for each tenant
        for tenant_id, tenant_db in tenants.items():
            # Create table
            await tenant_db.execute(
                """
                CREATE TABLE {{tables.metrics}} (
                    id SERIAL PRIMARY KEY,
                    metric_name VARCHAR(100),
                    value FLOAT,
                    recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Insert tenant-specific data
            await tenant_db.execute(
                """
                INSERT INTO {{tables.metrics}} (metric_name, value)
                VALUES ($1, $2), ($3, $4)
                """,
                "cpu_usage",
                45.5 + ord(tenant_id[0]) % 10,  # Different values per tenant
                "memory_usage",
                60.0 + ord(tenant_id[0]) % 20,
            )

        # Verify each tenant has isolated data
        for tenant_id, tenant_db in tenants.items():
            metrics = await tenant_db.fetch_all(
                "SELECT metric_name, value FROM {{tables.metrics}} ORDER BY metric_name"
            )

            assert len(metrics) == 2
            # Each tenant should have different values
            assert metrics[0]["value"] != metrics[1]["value"]

            # Verify data is in correct schema
            schema_check = await test_db.fetch_value(
                """
                SELECT table_schema
                FROM information_schema.tables
                WHERE table_schema = $1 AND table_name = 'metrics'
                """,
                tenant_id,
            )
            assert schema_check == tenant_id

    @pytest.mark.asyncio
    async def test_dynamic_tenant_creation(self, test_db):
        """Test creating new tenants dynamically."""

        async def onboard_new_tenant(tenant_id: str, tenant_name: str):
            """Simulate onboarding a new tenant."""
            # Create schema
            await test_db.execute(f'CREATE SCHEMA IF NOT EXISTS "{tenant_id}"')

            # Create tenant manager
            tenant_db = AsyncDatabaseManager(pool=test_db._pool, schema=tenant_id)

            # Create tenant tables
            await tenant_db.execute(
                """
                CREATE TABLE {{tables.tenant_info}} (
                    id SERIAL PRIMARY KEY,
                    tenant_id VARCHAR(50) UNIQUE NOT NULL,
                    tenant_name VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    settings JSONB DEFAULT '{}'::jsonb
                )
            """
            )

            await tenant_db.execute(
                """
                CREATE TABLE {{tables.users}} (
                    id SERIAL PRIMARY KEY,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    full_name VARCHAR(255),
                    role VARCHAR(50),
                    is_active BOOLEAN DEFAULT true
                )
            """
            )

            # Insert tenant info
            await tenant_db.execute(
                """
                INSERT INTO {{tables.tenant_info}} (tenant_id, tenant_name, settings)
                VALUES ($1, $2, $3::jsonb)
                """,
                tenant_id,
                tenant_name,
                '{"plan": "starter", "max_users": 10}',
            )

            return tenant_db

        # Onboard multiple tenants
        new_tenants = [
            ("tenant_123", "Startup ABC"),
            ("tenant_456", "Enterprise XYZ"),
            ("tenant_789", "SMB Solutions"),
        ]

        for tenant_id, tenant_name in new_tenants:
            tenant_db = await onboard_new_tenant(tenant_id, tenant_name)

            # Verify tenant setup
            info = await tenant_db.fetch_one(
                "SELECT * FROM {{tables.tenant_info}} WHERE tenant_id = $1", tenant_id
            )

            assert info["tenant_name"] == tenant_name

            # Parse settings if it's a string (JSONB handling varies)
            import json

            settings = info["settings"]
            if isinstance(settings, str):
                settings = json.loads(settings)
            assert settings["plan"] == "starter"

            # Add initial admin user
            await tenant_db.execute(
                """
                INSERT INTO {{tables.users}} (email, full_name, role)
                VALUES ($1, $2, 'admin')
                """,
                f"admin@{tenant_id}.com",
                f"Admin for {tenant_name}",
            )

    @pytest.mark.asyncio
    async def test_schema_migration_per_tenant(self, test_db):
        """Test running migrations for specific tenant schemas."""
        import os
        import tempfile

        from pgdbm import AsyncMigrationManager

        # Create temp directory for migrations
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a migration file
            migration_content = """
            CREATE TABLE {{tables.app_config}} (
                key VARCHAR(100) PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            INSERT INTO {{tables.app_config}} (key, value) VALUES
            ('version', '1.0.0'),
            ('feature_flags', '{"new_ui": false}');
            """

            migration_file = os.path.join(tmpdir, "001_initial_config.sql")
            with open(migration_file, "w") as f:
                f.write(migration_content)

            # Create two tenant schemas
            for tenant in ["tenant_one", "tenant_two"]:
                await test_db.execute(f'CREATE SCHEMA IF NOT EXISTS "{tenant}"')

                # Create tenant-specific manager
                tenant_db = AsyncDatabaseManager(pool=test_db._pool, schema=tenant)

                # Run migrations for this tenant
                migrations = AsyncMigrationManager(
                    tenant_db,
                    migrations_path=tmpdir,
                    module_name=tenant,  # Use tenant as module name
                )

                # Apply migrations
                result = await migrations.apply_pending_migrations()
                assert result["status"] == "success"
                assert len(result["applied"]) == 1

                # Verify migration was applied
                config = await tenant_db.fetch_all(
                    "SELECT * FROM {{tables.app_config}} ORDER BY key"
                )
                assert len(config) == 2
                assert config[1]["key"] == "version"
                assert config[1]["value"] == "1.0.0"
