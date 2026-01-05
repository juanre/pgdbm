# pgdbm CLI Reference

The pgdbm CLI provides powerful database management commands with special focus on dual-mode libraries and multi-module applications.

## Installation

```bash
# Install with CLI support
pip install pgdbm[cli]

# Or with uv
uv add pgdbm[cli]
```

## Quick Start

```bash
# Generate configuration
pgdbm generate config

# Create database
pgdbm db create

# Apply migrations
pgdbm migrate apply

# Start development
pgdbm dev start
```

## Core Commands

### Database Management

```bash
# Create database
pgdbm db create [--env dev|test|prod]

# Drop database (with confirmation)
pgdbm db drop [--confirm]

# Reset database (drop and recreate)
pgdbm db reset

# Test connection
pgdbm db test-connection

# Show database info
pgdbm db info
```

### Migration Management

```bash
# Apply pending migrations
pgdbm migrate apply [--module MODULE] [--all] [--dry-run]

# Show migration status
pgdbm migrate status [--module MODULE] [--all-modules]

# Create new migration
pgdbm migrate create NAME [--module MODULE] [--path PATH]

# Rollback migrations (requires down migrations)
pgdbm migrate rollback --module MODULE --version VERSION
```

### Schema Management

```bash
# List all schemas
pgdbm schema list

# Create schema for module
pgdbm schema create --module MODULE [--name NAME]

# Show schema dependencies
pgdbm schema deps --module MODULE

# Clean unused schemas
pgdbm schema clean [--dry-run]
```

### Development Workflow

```bash
# Start development environment
pgdbm dev start

# Watch for migration changes
pgdbm dev watch [--interval SECONDS]

# Reset development database
pgdbm dev reset

# Export schema to SQL
pgdbm dev export-schema [--output FILE] [--schema SCHEMA]
```

### Code Generation

```bash
# Generate dual-mode library
pgdbm generate library NAME [--dual-mode] [--with-api] [--path PATH]

# Generate test fixtures
pgdbm generate tests

# Generate configuration file
pgdbm generate config [--name PROJECT_NAME]
```

## Configuration

### pgdbm.toml Format

```toml
[project]
name = "my_project"
default_env = "dev"

[database]
migrations_table = "schema_migrations"

# Environment configurations
[environments.dev]
host = "localhost"
port = 5432
database = "myapp_dev"
user = "postgres"
password = "secret"  # Or use ${ENV_VAR}
schema = "public"

[environments.test]
url = "postgresql://localhost/myapp_test"
schema = "test"

[environments.prod]
url = "${DATABASE_URL}"  # From environment variable
schema = "production"
ssl_enabled = true
ssl_mode = "verify-full"
ssl_ca_file = "/etc/ssl/certs/ca.pem"

# Module configurations
[modules.users]
migrations_path = "src/users/migrations"
schema = "users"
mode = "dual"  # standalone | library | dual
depends_on = []

[modules.billing]
migrations_path = "src/billing/migrations"
schema = "billing"
mode = "library"
depends_on = ["users"]  # Migration dependencies

# Shared pool configuration
[shared_pool]
min_connections = 50
max_connections = 100
modules = ["users", "billing"]
```

### Environment Variables

- `PGDBM_CONFIG` - Path to configuration file (default: pgdbm.toml)
- `PGDBM_ENV` - Environment to use (default: dev)
- `DATABASE_URL` - Can be referenced in config as ${DATABASE_URL} and used directly in simple mode

## Multi-Module Applications

### Module Dependencies

pgdbm automatically resolves module dependencies:

```bash
# Apply migrations in dependency order
pgdbm migrate apply --all

# Output:
# Resolved module order: core → users → billing
# ✓ core: 001_initial.sql
# ✓ users: 001_users.sql
# ✓ billing: 001_subscriptions.sql
```

### Schema Isolation

Each module can have its own schema:

```toml
[modules.users]
schema = "users"

[modules.billing]
schema = "billing"
```

This creates isolated namespaces:
- `users.users` table
- `billing.invoices` table

## Dual-Mode Libraries

### Generate a Dual-Mode Service

```bash
pgdbm generate library my_service --dual-mode --with-api
```

This creates:
- Dual-mode database support
- FastAPI integration (optional)
- CLI for standalone operation
- Test fixtures for both modes
- Migration templates

### Using Generated Service

**Standalone mode:**
```bash
cd my_service
pip install -e .
pgdbm migrate apply
python -m src.my_service.cli serve
```

**Library mode:**
```python
from my_service import create_app
from pgdbm import AsyncDatabaseManager

# Use with shared database
shared_db = AsyncDatabaseManager(config)
app = create_app(db_manager=shared_db)
```

## Development Workflow

### Typical Development Cycle

```bash
# 1. Start development environment
pgdbm dev start

# 2. Create a migration
pgdbm migrate create add_user_table

# 3. Edit the migration file
# vim migrations/001_add_user_table.sql

# 4. Apply migration
pgdbm migrate apply

# 5. Watch for changes (in another terminal)
pgdbm dev watch

# 6. Export schema for documentation
pgdbm dev export-schema --output schema.sql
```

### Testing Both Modes

Generated test fixtures support both modes:

```python
@pytest_asyncio.fixture(params=["standalone", "library"])
async def dual_mode_service(request):
    mode = request.param
    # Tests run in both configurations
```

## Examples

### Simple Project

```bash
# No configuration needed
mkdir myproject && cd myproject
mkdir migrations

# Set connection string for simple mode
export DATABASE_URL="postgresql://user:password@localhost/myproject"

# Create first migration
pgdbm migrate create initial_schema

# Apply migrations
pgdbm migrate apply
```

### Multi-Module Project

```bash
# Generate config
pgdbm generate config --name platform

# Edit pgdbm.toml with modules
vim pgdbm.toml

# Create database
pgdbm db create

# Apply all modules
pgdbm migrate apply --all

# Check status
pgdbm migrate status --all-modules
```

### Dual-Mode Library

```bash
# Generate library scaffold
pgdbm generate library auth_service --dual-mode --with-api

# Navigate to library
cd auth_service

# Install dependencies
pip install -e .

# Create database
pgdbm db create

# Apply migrations
pgdbm migrate apply

# Run standalone
python -m src.auth_service.cli serve
```

## Best Practices

1. **Use Configuration Files**: Create `pgdbm.toml` for complex projects
2. **Module Naming**: Use unique, descriptive module names
3. **Schema Isolation**: Use separate schemas for different modules
4. **Dependency Order**: Define `depends_on` for correct migration order
5. **Test Both Modes**: Always test dual-mode libraries in both configurations
6. **Version Control**: Commit migrations and `pgdbm.toml`

## Troubleshooting

### Connection Issues

```bash
# Test connection
pgdbm db test-connection

# Check configuration
pgdbm --config pgdbm.toml --env dev db info
```

### Migration Problems

```bash
# Check status
pgdbm migrate status --module mymodule

# Dry run to see what would be applied
pgdbm migrate apply --dry-run
```

### Schema Conflicts

```bash
# List schemas and modules
pgdbm schema list

# Check dependencies
pgdbm schema deps --module mymodule
```

## Command Reference

Run `pgdbm --help` for full command listing:

```bash
pgdbm --help                    # General help
pgdbm db --help                 # Database commands
pgdbm migrate --help            # Migration commands
pgdbm schema --help             # Schema commands
pgdbm dev --help                # Development commands
pgdbm generate --help           # Generation commands
```

## Integration with CI/CD

### GitHub Actions

```yaml
- name: Install pgdbm
  run: pip install pgdbm[cli]

- name: Create test database
  run: pgdbm db create --env test

- name: Apply migrations
  run: pgdbm migrate apply --env test --all

- name: Run tests
  run: pytest
```

### Docker

```dockerfile
FROM python:3.11

# Install pgdbm with CLI
RUN pip install pgdbm[cli]

# Copy configuration
COPY pgdbm.toml .
COPY migrations/ migrations/

# Apply migrations on startup
CMD ["sh", "-c", "pgdbm migrate apply --env prod && python app.py"]
```
