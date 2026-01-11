# Copyright (c) 2025 Juan Reyero
# Licensed under the MIT License

# ABOUTME: Database migration manager with version tracking, checksum validation, and module-specific migration support.
# ABOUTME: Provides AsyncMigrationManager and Migration classes for applying SQL migrations with template substitution.

"""
Async database migration management with tracking and debugging.
"""

import hashlib
import logging
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel

from pgdbm.core import AsyncDatabaseManager
from pgdbm.errors import MigrationError

logger = logging.getLogger(__name__)


class Migration(BaseModel):
    """Represents a database migration."""

    filename: str
    checksum: str
    content: str
    applied_at: Optional[datetime] = None
    module_name: Optional[str] = None

    @property
    def is_applied(self) -> bool:
        """Check if migration has been applied."""
        return self.applied_at is not None

    @property
    def version(self) -> str:
        """Extract version from filename (e.g., '001' from '001_create_users.sql')."""
        # Common patterns: 001_name.sql, V1__name.sql, 20231225_name.sql

        # Try numeric prefix pattern (001_)
        match = re.match(r"^(\d+)_", self.filename)
        if match:
            return match.group(1)

        # Try Flyway pattern (V1__)
        match = re.match(r"^V(\d+)__", self.filename)
        if match:
            return match.group(1)

        # Try timestamp pattern (20231225120000_)
        match = re.match(r"^(\d{8,14})_", self.filename)
        if match:
            return match.group(1)

        # If no pattern matches, use the filename itself
        return self.filename.split(".")[0]


def _split_sql_statements(sql: str) -> list[str]:
    """Split SQL into individual statements for autocommit execution.

    Handles:
    - Single-quoted strings ('...') with escaped quotes ('')
    - Dollar-quoted strings ($$...$$ or $tag$...$tag$)
    - SQL comments (-- and /* */)

    Returns non-empty statements only.
    """
    statements = []
    current = []
    i = 0
    length = len(sql)

    while i < length:
        char = sql[i]

        # Single-line comment: skip to end of line
        if char == "-" and i + 1 < length and sql[i + 1] == "-":
            start = i
            while i < length and sql[i] != "\n":
                i += 1
            current.append(sql[start:i])
            continue

        # Block comment: skip to */
        if char == "/" and i + 1 < length and sql[i + 1] == "*":
            start = i
            i += 2
            while i + 1 < length and not (sql[i] == "*" and sql[i + 1] == "/"):
                i += 1
            i += 2  # Skip */
            current.append(sql[start:i])
            continue

        # Single-quoted string: handle escaped quotes ('')
        if char == "'":
            start = i
            i += 1
            while i < length:
                if sql[i] == "'":
                    if i + 1 < length and sql[i + 1] == "'":
                        i += 2  # Skip escaped quote
                    else:
                        i += 1  # End of string
                        break
                else:
                    i += 1
            current.append(sql[start:i])
            continue

        # Dollar-quoted string: $$...$$ or $tag$...$tag$
        if char == "$":
            # Find the tag (empty for $$ or alphanumeric for $tag$)
            tag_start = i
            i += 1
            while i < length and (sql[i].isalnum() or sql[i] == "_"):
                i += 1
            if i < length and sql[i] == "$":
                i += 1
                tag = sql[tag_start:i]
                # Find matching closing tag
                start = tag_start
                end_pos = sql.find(tag, i)
                if end_pos != -1:
                    i = end_pos + len(tag)
                    current.append(sql[start:i])
                    continue
                else:
                    # Unclosed dollar quote - take rest of string
                    current.append(sql[start:])
                    break
            else:
                # Not a dollar quote, just a $ character
                i = tag_start + 1
                current.append("$")
                continue

        # Statement separator
        if char == ";":
            current.append(char)
            stmt = "".join(current).strip()
            if stmt and stmt != ";":
                statements.append(stmt)
            current = []
            i += 1
            continue

        # Regular character
        current.append(char)
        i += 1

    # Handle final statement without trailing semicolon
    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)

    return statements


class AsyncMigrationManager:
    """Manages database migrations asynchronously with detailed debugging support."""

    def __init__(
        self,
        db_manager: AsyncDatabaseManager,
        migrations_path: str = "./migrations",
        migrations_table: str = "schema_migrations",
        module_name: Optional[str] = None,
        **kwargs: Any,
    ) -> None:
        # Check for common mistake: passing schema parameter
        if "schema" in kwargs:
            raise TypeError(
                "AsyncMigrationManager doesn't take a 'schema' parameter.\n"
                "The schema should be configured in the AsyncDatabaseManager instead:\n\n"
                "  # Correct usage:\n"
                "  db = AsyncDatabaseManager(pool=shared_pool, schema='myschema')\n"
                "  migrations = AsyncMigrationManager(db, migrations_path='./migrations')\n\n"
                "The migration manager will use the schema from the database manager."
            )

        # Check for other unexpected parameters
        if kwargs:
            unexpected = ", ".join(kwargs.keys())
            raise TypeError(
                f"AsyncMigrationManager got unexpected keyword arguments: {unexpected}\n"
                f"Valid parameters are: db_manager, migrations_path, migrations_table, module_name"
            )

        self.db = db_manager
        # Validate and resolve migration path to prevent directory traversal
        self.migrations_path = Path(migrations_path).resolve()

        # Validate migrations table name
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]{0,62}$", migrations_table):
            raise MigrationError(
                f"Invalid migrations table name '{migrations_table}'. Table names must start "
                "with a letter or underscore and contain only letters, numbers, and underscores."
            )

        self.migrations_table = migrations_table
        self.module_name = module_name or self.db.schema or "default"
        self._debug = os.environ.get("MIGRATION_DEBUG", "").lower() in (
            "1",
            "true",
            "yes",
        )

    async def ensure_migrations_table(self) -> None:
        """Create migrations tracking table if it doesn't exist."""
        table_name = self.migrations_table
        if self.db.schema:
            table_name = f"{self.db.schema}.{self.migrations_table}"

        await self.db.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                checksum VARCHAR(64) NOT NULL,
                module_name VARCHAR(100),
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                applied_by VARCHAR(100) DEFAULT CURRENT_USER,
                execution_time_ms INTEGER,
                UNIQUE(filename, module_name)
            )
        """
        )

        # Add index for faster lookups
        await self.db.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{self.migrations_table}_module
            ON {table_name}(module_name, filename)
        """
        )

        if self._debug:
            logger.debug(f"Ensured migrations table '{table_name}' exists")

    async def _ensure_migrations_table_on(self, conn: Any) -> None:
        """Create migrations tracking table using a specific connection."""
        table_name = self.migrations_table
        if self.db.schema:
            table_name = f"{self.db.schema}.{self.migrations_table}"

        await conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                id SERIAL PRIMARY KEY,
                filename VARCHAR(255) NOT NULL,
                checksum VARCHAR(64) NOT NULL,
                module_name VARCHAR(100),
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                applied_by VARCHAR(100) DEFAULT CURRENT_USER,
                execution_time_ms INTEGER,
                UNIQUE(filename, module_name)
            )
        """
        )

        await conn.execute(
            f"""
            CREATE INDEX IF NOT EXISTS idx_{self.migrations_table}_module
            ON {table_name}(module_name, filename)
        """
        )

    async def get_applied_migrations(self) -> dict[str, Migration]:
        """Get list of applied migrations for this module."""
        table_name = self.migrations_table
        if self.db.schema:
            table_name = f"{self.db.schema}.{self.migrations_table}"

        rows = await self.db.fetch_all(
            f"""
            SELECT filename, checksum, applied_at, module_name
            FROM {table_name}
            WHERE module_name = $1 OR module_name IS NULL
            ORDER BY filename
            """,
            self.module_name,
        )

        migrations = {}
        for row in rows:
            migration = Migration(
                filename=row["filename"],
                checksum=row["checksum"],
                content="",  # Not loaded from DB
                applied_at=row["applied_at"],
                module_name=row["module_name"],
            )
            migrations[row["filename"]] = migration

        if self._debug:
            logger.debug(
                f"Found {len(migrations)} applied migrations for module '{self.module_name}'"
            )

        return migrations

    async def _get_applied_migrations_on(self, conn: Any) -> dict[str, Migration]:
        """Get applied migrations using a specific connection."""
        table_name = self.migrations_table
        if self.db.schema:
            table_name = f"{self.db.schema}.{self.migrations_table}"

        rows = await conn.fetch(
            f"""
            SELECT filename, checksum, applied_at, module_name
            FROM {table_name}
            WHERE module_name = $1 OR module_name IS NULL
            ORDER BY filename
            """,
            self.module_name,
        )

        migrations: dict[str, Migration] = {}
        for row in rows:
            d = dict(row)
            migration = Migration(
                filename=d["filename"],
                checksum=d["checksum"],
                content="",
                applied_at=d["applied_at"],
                module_name=d["module_name"],
            )
            migrations[d["filename"]] = migration

        if self._debug:
            logger.debug(
                f"Found {len(migrations)} applied migrations for module '{self.module_name}' (conn)"
            )
        return migrations

    def _calculate_checksum(self, content: str) -> str:
        """Calculate SHA256 checksum of migration content."""
        # Normalize line endings for consistent checksums
        normalized_content = content.replace("\r\n", "\n").strip()
        return hashlib.sha256(normalized_content.encode("utf-8")).hexdigest()

    def _requires_no_transaction(self, content: str) -> bool:
        """Check if migration declares no-transaction mode.

        Migrations containing DDL that cannot run inside a transaction block
        (like CREATE INDEX CONCURRENTLY) should include the magic comment
        at the start of a line:

            -- pgdbm:no-transaction

        This causes the migration to execute in autocommit mode.
        """
        return bool(re.search(r"^-- pgdbm:no-transaction(?=\s|$)", content, re.MULTILINE))

    async def _validate_migration_syntax(self, content: str, filename: str) -> None:
        """Validate migration SQL syntax without executing."""
        # Basic syntax validation - more sophisticated validation would
        # require parsing the SQL, which is complex
        # For now, just check for basic issues
        if not content.strip():
            raise MigrationError(f"Migration '{filename}' is empty", migration_file=filename)

    async def apply_migration(self, migration: Migration) -> float:
        """
        Apply a single migration and return execution time in milliseconds.

        If the migration contains '-- pgdbm:no-transaction' at the start of a line,
        it will be executed in autocommit mode (no transaction wrapper). This is
        required for DDL that cannot run inside a transaction block, such as
        CREATE INDEX CONCURRENTLY.

        Returns:
            Execution time in milliseconds
        """
        # Check if migration requires no-transaction mode
        if self._requires_no_transaction(migration.content):
            async with self.db.acquire() as conn:
                return await self._apply_migration_no_transaction(conn, migration)

        # Standard transactional path
        import time

        start_time = time.time()

        if self._debug:
            logger.debug(f"Applying migration: {migration.filename}")
            logger.debug(f"Content preview: {migration.content[:200]}...")

        # Validate syntax first
        await self._validate_migration_syntax(migration.content, migration.filename)

        table_name = self.migrations_table
        if self.db.schema:
            table_name = f"{self.db.schema}.{self.migrations_table}"

        async with self.db.transaction() as tx:
            # Execute migration - TransactionManager automatically processes {{tables.}} placeholders
            await tx.execute(migration.content)

            # Calculate execution time before recording
            execution_time_ms = int((time.time() - start_time) * 1000)
            # Ensure at least 1ms for very fast operations
            if execution_time_ms == 0:
                execution_time_ms = 1

            await tx.execute(
                f"""
                INSERT INTO {table_name}
                (filename, checksum, module_name, execution_time_ms)
                VALUES ($1, $2, $3, $4)
                """,
                migration.filename,
                migration.checksum,
                self.module_name,
                execution_time_ms,
            )

        logger.info(f"Applied migration '{migration.filename}' in {execution_time_ms}ms")
        return execution_time_ms

    async def _apply_migration_on(self, conn: Any, migration: Migration) -> float:
        """Apply a single migration using a specific connection.

        If the migration contains '-- pgdbm:no-transaction', it will be executed
        in autocommit mode (no transaction wrapper). This is required for DDL
        that cannot run inside a transaction block, such as:
        - CREATE INDEX CONCURRENTLY
        - DROP INDEX CONCURRENTLY
        - REINDEX CONCURRENTLY
        """
        # Check if migration requires no-transaction mode
        if self._requires_no_transaction(migration.content):
            return await self._apply_migration_no_transaction(conn, migration)

        # Standard transactional path
        import time

        start_time = time.time()

        if self._debug:
            logger.debug(f"Applying migration: {migration.filename}")
            logger.debug(f"Content preview: {migration.content[:200]}...")

        await self._validate_migration_syntax(migration.content, migration.filename)

        table_name = self.migrations_table
        if self.db.schema:
            table_name = f"{self.db.schema}.{self.migrations_table}"

        # This method receives a raw connection, so we need to manually prepare the query
        processed_content = self.db.prepare_query(migration.content)

        async with conn.transaction():
            await conn.execute(processed_content)

            execution_time_ms = int((time.time() - start_time) * 1000)
            if execution_time_ms == 0:
                execution_time_ms = 1

            await conn.execute(
                f"""
                INSERT INTO {table_name}
                (filename, checksum, module_name, execution_time_ms)
                VALUES ($1, $2, $3, $4)
                """,
                migration.filename,
                migration.checksum,
                self.module_name,
                execution_time_ms,
            )

        logger.info(f"Applied migration '{migration.filename}' in {execution_time_ms}ms")
        return execution_time_ms

    async def _apply_migration_no_transaction(self, conn: Any, migration: Migration) -> float:
        """Apply a migration without transaction wrapper (autocommit mode).

        Used for DDL that cannot run inside a transaction block:
        - CREATE INDEX CONCURRENTLY
        - DROP INDEX CONCURRENTLY
        - REINDEX CONCURRENTLY

        The migration file must include the magic comment at the start of a line:
            -- pgdbm:no-transaction

        IMPORTANT: Statements in no-transaction migrations should be idempotent
        (e.g., use IF NOT EXISTS). If a statement fails partway through, earlier
        statements will already be committed and cannot be rolled back. On retry,
        idempotent statements become no-ops, allowing the migration to continue.
        """
        import time

        start_time = time.time()

        logger.warning(
            f"Applying migration '{migration.filename}' in no-transaction mode. "
            "Partial failures cannot be rolled back - ensure statements are idempotent."
        )

        if self._debug:
            logger.debug(f"Content preview: {migration.content[:200]}...")

        await self._validate_migration_syntax(migration.content, migration.filename)

        table_name = self.migrations_table
        if self.db.schema:
            table_name = f"{self.db.schema}.{self.migrations_table}"

        # Process template placeholders
        processed_content = self.db.prepare_query(migration.content)

        # Split into individual statements and execute each separately.
        # asyncpg wraps multiple statements in an implicit transaction,
        # which breaks CREATE INDEX CONCURRENTLY. Single statements
        # execute in true autocommit mode.
        statements = _split_sql_statements(processed_content)
        for stmt in statements:
            if self._debug:
                logger.debug(f"Executing statement: {stmt[:100]}...")
            await conn.execute(stmt)

        execution_time_ms = int((time.time() - start_time) * 1000)
        if execution_time_ms == 0:
            execution_time_ms = 1

        # Record in migrations table (also in autocommit mode)
        await conn.execute(
            f"""
            INSERT INTO {table_name}
            (filename, checksum, module_name, execution_time_ms)
            VALUES ($1, $2, $3, $4)
            """,
            migration.filename,
            migration.checksum,
            self.module_name,
            execution_time_ms,
        )

        logger.info(f"Applied migration '{migration.filename}' in {execution_time_ms}ms")
        return execution_time_ms

    async def find_migration_files(self) -> list[Migration]:
        """Find all migration files in the migrations directory."""
        if not self.migrations_path.exists():
            logger.warning(f"Migrations directory '{self.migrations_path}' does not exist")
            return []

        migration_files = sorted(
            [
                f
                for f in self.migrations_path.glob("*.sql")
                if f.is_file() and not f.name.startswith(".")
            ]
        )

        migrations = []
        for migration_file in migration_files:
            try:
                # Ensure the file is within the migrations directory
                migration_file = migration_file.resolve()
                if not migration_file.is_relative_to(self.migrations_path):
                    raise MigrationError(
                        f"Migration file '{migration_file}' is outside the migrations directory",
                        migration_file=str(migration_file),
                    )

                content = migration_file.read_text(encoding="utf-8")
                checksum = self._calculate_checksum(content)

                migration = Migration(
                    filename=migration_file.name, checksum=checksum, content=content
                )
                migrations.append(migration)

            except Exception as e:
                logger.error(f"Failed to read migration file '{migration_file}': {e}")
                raise

        if self._debug:
            logger.debug(f"Found {len(migrations)} migration files")

        return migrations

    async def get_pending_migrations(self) -> list[Migration]:
        """Get list of migrations that haven't been applied yet."""
        applied = await self.get_applied_migrations()
        all_migrations = await self.find_migration_files()

        pending = []
        for migration in all_migrations:
            if migration.filename in applied:
                # Check if migration was modified
                if applied[migration.filename].checksum != migration.checksum:
                    raise MigrationError(
                        f"Migration '{migration.filename}' has been modified after being applied!\n"
                        f"Expected checksum: {applied[migration.filename].checksum}\n"
                        f"Current checksum: {migration.checksum}",
                        migration_file=migration.filename,
                    )
            else:
                pending.append(migration)

        return pending

    async def apply_pending_migrations(self, dry_run: bool = False) -> dict[str, Any]:
        """
        Apply all pending migrations.

        Args:
            dry_run: If True, only show what would be applied without executing

        Returns:
            Dictionary with migration results
        """
        # Serialize migration application per module: use namespaced advisory lock
        lock_key_query = "SELECT pg_advisory_lock(hashtext('pgdbm_migration_' || $1))"
        unlock_query = "SELECT pg_advisory_unlock(hashtext('pgdbm_migration_' || $1))"
        async with self.db.acquire() as conn:
            await conn.execute(lock_key_query, self.module_name)
            try:
                await self._ensure_migrations_table_on(conn)
                applied = await self._get_applied_migrations_on(conn)
                all_migrations = await self.find_migration_files()

                pending: list[Migration] = []
                for migration in all_migrations:
                    if migration.filename in applied:
                        if applied[migration.filename].checksum != migration.checksum:
                            raise MigrationError(
                                f"Migration '{migration.filename}' has been modified after being applied!\n"
                                f"Expected checksum: {applied[migration.filename].checksum}\n"
                                f"Current checksum: {migration.checksum}",
                                migration_file=migration.filename,
                            )
                    else:
                        pending.append(migration)
                if not pending:
                    logger.info("No pending migrations to apply")
                    return {
                        "status": "up_to_date",
                        "applied": [],
                        "skipped": list(applied.keys()),
                        "total": len(applied),
                    }

                if dry_run:
                    logger.info(f"DRY RUN: Would apply {len(pending)} migrations:")
                    for migration in pending:
                        logger.info(f"  - {migration.filename}")
                    return {
                        "status": "dry_run",
                        "pending": [m.filename for m in pending],
                        "applied": [],
                        "skipped": list(applied.keys()),
                        "total": len(pending) + len(applied),
                    }

                applied_migrations: list[dict[str, Any]] = []
                total_time_ms = 0.0

                for migration in pending:
                    try:
                        execution_time = await self._apply_migration_on(conn, migration)
                        applied_migrations.append(
                            {
                                "filename": migration.filename,
                                "execution_time_ms": execution_time,
                            }
                        )
                        total_time_ms += execution_time

                    except Exception as e:
                        logger.error(f"Failed to apply migration '{migration.filename}': {e}")
                        return {
                            "status": "error",
                            "error": str(e),
                            "failed_migration": migration.filename,
                            "applied": applied_migrations,
                            "skipped": list(applied.keys()),
                            "total": len(applied) + len(pending),
                        }

                logger.info(
                    f"Successfully applied {len(applied_migrations)} migrations "
                    f"in {total_time_ms}ms"
                )

                return {
                    "status": "success",
                    "applied": applied_migrations,
                    "skipped": list(applied.keys()),
                    "total": len(applied) + len(applied_migrations),
                    "total_time_ms": total_time_ms,
                }
            finally:
                try:
                    await conn.execute(unlock_query, self.module_name)
                except Exception:
                    pass

    async def create_migration(self, name: str, content: str, auto_transaction: bool = True) -> str:
        """
        Create a new migration file.

        Args:
            name: Migration name (will be prefixed with timestamp)
            content: SQL content
            auto_transaction: Whether to wrap in transaction

        Returns:
            Path to created migration file
        """
        # Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{name}.sql"
        filepath = self.migrations_path / filename

        # Ensure migrations directory exists
        self.migrations_path.mkdir(parents=True, exist_ok=True)

        # Add transaction wrapper if requested
        if auto_transaction and "BEGIN" not in content.upper():
            content = f"BEGIN;\n\n{content}\n\nCOMMIT;"

        # Write migration file
        filepath.write_text(content, encoding="utf-8")
        logger.info(f"Created migration: {filepath}")

        return str(filepath)

    async def rollback_migration(self, filename: str) -> None:
        """
        Mark a migration as not applied (does not undo changes).

        This is useful for development when you need to re-run a migration.
        """
        table_name = self.migrations_table
        if self.db.schema:
            table_name = f"{self.db.schema}.{self.migrations_table}"

        result = await self.db.execute(
            f"""
            DELETE FROM {table_name}
            WHERE filename = $1 AND module_name = $2
            """,
            filename,
            self.module_name,
        )

        if "DELETE 0" in result:
            logger.warning(f"Migration '{filename}' was not found in applied migrations")
        else:
            logger.info(f"Rolled back migration record for '{filename}'")

    async def get_migration_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent migration history with execution details."""
        table_name = self.migrations_table
        if self.db.schema:
            table_name = f"{self.db.schema}.{self.migrations_table}"

        result: list[dict[str, Any]] = await self.db.fetch_all(
            f"""
            SELECT
                filename,
                module_name,
                applied_at,
                applied_by,
                execution_time_ms
            FROM {table_name}
            WHERE module_name = $1 OR module_name IS NULL
            ORDER BY applied_at DESC
            LIMIT $2
            """,
            self.module_name,
            limit,
        )
        return result
