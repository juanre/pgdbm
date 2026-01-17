"""
Security tests for pgdbm to verify protections against common vulnerabilities.
"""

import pytest

from pgdbm import (
    AsyncDatabaseManager,
    DatabaseConfig,
    DatabaseTestError,
    MigrationError,
    SchemaError,
)
from pgdbm.migrations import AsyncMigrationManager
from pgdbm.testing import AsyncTestDatabase


class TestSQLInjectionProtection:
    """Test protection against SQL injection attacks."""

    @pytest.mark.unit
    def test_schema_name_validation_prevents_injection(self):
        """Test that invalid schema names are rejected."""
        # Try to inject SQL via schema name
        malicious_schemas = [
            'public"; DROP TABLE users; --',
            "public' OR '1'='1",
            "public; DELETE FROM users WHERE 1=1; --",
            "public/*comment*/",
            "public-- comment",
            "123_invalid_start",
            "contains-hyphen",
            "contains space",
            "very_long_name_that_exceeds_postgresql_limit_of_63_characters_total",
        ]

        for malicious_schema in malicious_schemas:
            with pytest.raises(SchemaError) as exc_info:
                config = DatabaseConfig(schema=malicious_schema)
                db = AsyncDatabaseManager(config=config)
                db.prepare_query("SELECT * FROM {{tables.users}}")

            assert "Invalid schema name" in str(exc_info.value)
            assert malicious_schema in str(exc_info.value)

    @pytest.mark.unit
    def test_valid_schema_names_are_accepted(self):
        """Test that valid schema names work correctly."""
        valid_schemas = [
            "public",
            "my_schema",
            "schema123",
            "_private_schema",
            "CamelCaseSchema",
            "a" * 63,  # Max length
        ]

        for valid_schema in valid_schemas:
            config = DatabaseConfig(schema=valid_schema)
            db = AsyncDatabaseManager(config=config)

            # Should not raise
            query = db._prepare_query("SELECT * FROM {{tables.users}}")
            assert f'"{valid_schema}".users' in query

    @pytest.mark.unit
    def test_explicit_schema_validation_prevents_injection(self):
        """Test that invalid schema names in explicit table placeholders are rejected.

        Note: The template regex only captures [a-zA-Z0-9_]+ characters, so special
        characters won't match and are left as literal text. This tests identifiers
        that match the regex but fail validation (e.g., starting with a digit).
        """
        config = DatabaseConfig(schema=None)
        db = AsyncDatabaseManager(config=config)

        # These match [a-zA-Z0-9_]+ but fail validation (start with digit or too long)
        invalid_schemas = [
            "123_starts_with_digit",
            "9schema",
            "a" * 64,  # Exceeds 63 char limit
        ]

        for invalid_schema in invalid_schemas:
            with pytest.raises(SchemaError) as exc_info:
                db.prepare_query(f"SELECT * FROM {{{{tables.{invalid_schema}.users}}}}")

            assert "Invalid schema name" in str(exc_info.value)

    @pytest.mark.unit
    def test_table_name_validation_prevents_injection(self):
        """Test that invalid table names in table placeholders are rejected.

        Note: The template regex only captures [a-zA-Z0-9_]+ characters, so special
        characters won't match and are left as literal text. This tests identifiers
        that match the regex but fail validation (e.g., starting with a digit).
        """
        config = DatabaseConfig(schema="test_schema")
        db = AsyncDatabaseManager(config=config)

        # These match [a-zA-Z0-9_]+ but fail validation (start with digit or too long)
        invalid_tables = [
            "123_starts_with_digit",
            "9users",
            "a" * 64,  # Exceeds 63 char limit
        ]

        for invalid_table in invalid_tables:
            with pytest.raises(SchemaError) as exc_info:
                db.prepare_query(f"SELECT * FROM {{{{tables.{invalid_table}}}}}")

            assert "Invalid table name" in str(exc_info.value)

    @pytest.mark.unit
    def test_explicit_table_name_validation_prevents_injection(self):
        """Test that invalid table names in explicit schema placeholders are rejected.

        Note: The template regex only captures [a-zA-Z0-9_]+ characters, so special
        characters won't match and are left as literal text. This tests identifiers
        that match the regex but fail validation (e.g., starting with a digit).
        """
        config = DatabaseConfig(schema=None)
        db = AsyncDatabaseManager(config=config)

        # These match [a-zA-Z0-9_]+ but fail validation (start with digit or too long)
        invalid_tables = [
            "123_starts_with_digit",
            "9users",
            "a" * 64,  # Exceeds 63 char limit
        ]

        for invalid_table in invalid_tables:
            with pytest.raises(SchemaError) as exc_info:
                db.prepare_query(f"SELECT * FROM {{{{tables.valid_schema.{invalid_table}}}}}")

            assert "Invalid table name" in str(exc_info.value)

    @pytest.mark.unit
    def test_special_chars_in_template_left_unchanged(self):
        """Test that placeholders with special chars are left as literal text.

        This is secure because invalid SQL syntax will cause a database error,
        not an injection. The regex only captures [a-zA-Z0-9_]+ characters.
        """
        config = DatabaseConfig(schema=None)
        db = AsyncDatabaseManager(config=config)

        # These contain chars outside [a-zA-Z0-9_] so won't match the regex
        malformed_templates = [
            "SELECT * FROM {{tables.bad; DROP.users}}",
            "SELECT * FROM {{tables.bad-schema.users}}",
            'SELECT * FROM {{tables.bad".users}}',
        ]

        for template in malformed_templates:
            result = db.prepare_query(template)
            # Should be unchanged - the placeholder wasn't recognized
            assert result == template

    @pytest.mark.unit
    def test_database_name_validation_in_testing(self):
        """Test that invalid database names are rejected in testing utilities."""
        test_db = AsyncTestDatabase()

        malicious_names = [
            'test"; DROP DATABASE production; --',
            "test' OR '1'='1",
            "test/*comment*/",
            "123test",  # Can't start with number
            "test-db",  # No hyphens
            "test db",  # No spaces
        ]

        for malicious_name in malicious_names:
            with pytest.raises(DatabaseTestError) as exc_info:
                # Use the internal method directly for testing
                test_db._test_db_name = malicious_name
                import asyncio

                asyncio.run(test_db._drop_database(None, malicious_name))

            assert "Invalid database name" in str(exc_info.value)

    @pytest.mark.unit
    def test_migration_table_name_validation(self):
        """Test that invalid migration table names are rejected."""
        config = DatabaseConfig()
        db = AsyncDatabaseManager(config=config)

        malicious_table_names = [
            'migrations"; DROP TABLE users; --',
            "migrations' OR '1'='1",
            "123_migrations",
            "migrations-table",
            "migrations table",
        ]

        for malicious_table in malicious_table_names:
            with pytest.raises(MigrationError) as exc_info:
                AsyncMigrationManager(db_manager=db, migrations_table=malicious_table)

            assert "Invalid migrations table name" in str(exc_info.value)


class TestPasswordSecurity:
    """Test password handling and masking."""

    @pytest.mark.unit
    def test_password_from_environment_variable(self, monkeypatch):
        """Test that password can be loaded from environment variable."""
        monkeypatch.setenv("DB_PASSWORD", "secret_password")

        config = DatabaseConfig(password=None)  # No password in config
        dsn = config.get_dsn()

        assert "secret_password" in dsn
        assert config.password is None  # Original config unchanged

    @pytest.mark.unit
    def test_password_url_encoding(self):
        """Test that special characters in passwords are properly encoded."""
        special_passwords = [
            "pass@word",
            "p@ss#word!",
            "pass word",
            "pass&word=123",
            "p%40ssw%3Drd",  # Already encoded chars
        ]

        for password in special_passwords:
            config = DatabaseConfig(password=password)
            dsn = config.get_dsn()

            # Password should be URL encoded in DSN
            assert password not in dsn or password == "p%40ssw%3Drd"
            assert "postgresql://" in dsn

    @pytest.mark.unit
    def test_dsn_password_masking(self):
        """Test that passwords are masked in log-friendly DSN."""
        config = DatabaseConfig(
            user="testuser", password="super_secret_password", host="localhost", database="testdb"
        )

        masked_dsn = config.get_dsn_masked()

        assert "super_secret_password" not in masked_dsn
        assert "****" in masked_dsn
        assert "testuser" in masked_dsn
        assert "localhost" in masked_dsn

    @pytest.mark.unit
    def test_connection_string_password_masking(self):
        """Test password masking in custom connection strings."""
        connection_strings = [
            "postgresql://user:password@localhost/db",
            "postgresql://admin:very_long_password_12345@server.com:5432/mydb",
            "postgres://user:p@ssw0rd!@host/database",
        ]

        for conn_str in connection_strings:
            config = DatabaseConfig(connection_string=conn_str)
            masked = config.get_dsn_masked()

            # Original passwords should be masked
            assert "password" not in masked
            assert "very_long_password_12345" not in masked
            assert "p@ssw0rd!" not in masked
            assert "****" in masked

    @pytest.mark.unit
    def test_sensitive_args_masking(self):
        """Test that sensitive arguments are masked in debug logs."""
        config = DatabaseConfig()
        db = AsyncDatabaseManager(config=config)

        # Test various argument types
        args = (
            "short",  # Short string - not masked
            "this_is_a_very_long_string_that_might_be_sensitive_data",  # Long string - masked
            123,  # Number - not masked
            None,  # None - not masked
            "another_very_long_password_or_api_key_12345",  # Long string - masked
        )

        masked = db._mask_sensitive_args(args)

        assert masked[0] == "short"  # Short strings unchanged
        assert "thi...ata" in str(masked[1])  # Long string masked
        assert masked[2] == 123  # Numbers unchanged
        assert masked[3] is None  # None unchanged
        assert "ano...345" in str(masked[4])  # Long string masked


class TestPathTraversalProtection:
    """Test protection against path traversal attacks."""

    @pytest.mark.asyncio
    async def test_migration_path_validation(self, tmp_path):
        """Test that migration files outside the migrations directory are rejected."""
        # Create a migrations directory
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()

        # Create a file outside migrations directory
        outside_file = tmp_path / "outside.sql"
        outside_file.write_text("DROP TABLE users;")

        # Create a proper migration file
        migration_file = migrations_dir / "001_test.sql"
        migration_file.write_text("CREATE TABLE test (id INT);")

        config = DatabaseConfig()
        db = AsyncDatabaseManager(config=config)
        migrations = AsyncMigrationManager(db_manager=db, migrations_path=str(migrations_dir))

        # The find_migration_files should only find files in migrations_dir
        found = await migrations.find_migration_files()
        assert len(found) == 1
        assert found[0].filename == "001_test.sql"


class TestErrorMessageSecurity:
    """Test that error messages don't leak sensitive information."""

    @pytest.mark.unit
    def test_query_error_truncates_long_queries(self):
        """Test that long queries are truncated in error messages."""
        from pgdbm.errors import QueryError

        long_query = "SELECT " + "x" * 300 + " FROM users"

        error = QueryError("Query failed", query=long_query, params=("param1", "param2"))

        error_str = str(error)
        assert len(error_str) < len(long_query) + 100  # Much shorter than original
        assert "..." in error_str  # Truncation indicator
        assert "SELECT" in error_str  # Beginning preserved

    @pytest.mark.unit
    def test_connection_error_shows_sanitized_info(self):
        """Test that connection errors show helpful but safe information."""
        from pgdbm.errors import ConnectionError

        error = ConnectionError(
            "Connection failed",
            host="secret.server.com",
            port=5432,
            database="production_db",
            attempts=3,
        )

        error_str = str(error)

        # Should contain troubleshooting tips
        assert "Check if PostgreSQL is running" in error_str
        assert "secret.server.com:5432" in error_str

        # Should NOT contain any passwords or sensitive data
        assert "password" not in error_str.lower()
