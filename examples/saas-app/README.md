# Row-Level Multi-Tenant SaaS Example

A multi-tenant SaaS application demonstrating row-level tenant isolation with pgdbm.

## Features

- ✅ Row-level multi-tenancy (all tenants share tables)
- ✅ Tenant provisioning and management
- ✅ User authentication with JWT
- ✅ Per-tenant data isolation via tenant_id columns
- ✅ Cross-tenant admin access
- ✅ Billing integration patterns
- ✅ Usage tracking and limits
- ✅ Optional Row-Level Security (RLS) policies

## Architecture

This example demonstrates a row-level multi-tenancy pattern where:
- All tenants share the same tables
- Each table has a `tenant_id` column for isolation
- Queries filter by `tenant_id` to ensure data isolation
- Admin users can query across all tenants
- Uses `{{tables.}}` syntax for flexible deployment

## Project Structure

```
saas-app/
├── README.md
├── requirements.txt
├── migrations/
│   └── 001_unified_schema.sql  # All tables with tenant_id columns
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application
│   ├── config.py               # Configuration
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py             # Base database wrapper
│   │   ├── tenant.py           # Tenant-specific queries
│   │   └── admin.py            # Admin database access
│   ├── models/
│   │   ├── __init__.py
│   │   ├── tenant.py           # Tenant models
│   │   ├── user.py             # User models
│   │   └── project.py          # Project models
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py             # Authentication endpoints
│   │   ├── tenants.py          # Tenant management
│   │   ├── projects.py         # Projects API (filtered by tenant)
│   │   └── admin.py            # Admin endpoints
│   └── middleware/
│       ├── __init__.py
│       └── tenant.py           # Tenant context middleware
└── tests/
    ├── conftest.py
    ├── test_tenant.py
    ├── test_auth.py
    └── test_projects.py
```

## Setup

1. Create database:
```bash
createdb saas_app
```

2. Set environment variables (optional):
```bash
# Default: postgresql://postgres:postgres@localhost/saas_app
export DATABASE_URL="postgresql://user:password@localhost/saas_app"
export JWT_SECRET="your-secret-key"
export APP_ENV="development"
```

Note: The app will use sensible defaults if these aren't set.

3. Install dependencies:
```bash
# Install using uv (recommended)
uv add -r requirements.txt

# Or using pip
pip install -r requirements.txt
```

4. Run public schema migrations:
```bash
python -m app.db.admin migrate_public
```

You can also create tenants via CLI:
```bash
python -m app.db.admin create_tenant acme "Acme Corp" admin@acme.com pro
```

5. Run the application:
```bash
uvicorn app.main:app --reload
```

## API Flow

### 1. Create a Tenant
```bash
curl -X POST http://localhost:8000/api/tenants \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Corp",
    "slug": "acme",
    "email": "admin@acme.com",
    "plan": "pro"
  }'
```

### 2. Authenticate
```bash
curl -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@acme.com",
    "password": "password"
  }'
```

### 3. Access Tenant Data
```bash
# Use the JWT token from login
curl http://localhost:8000/api/projects \
  -H "Authorization: Bearer <token>"
```

## Key Patterns

### Row-Level Isolation (tenant_id)

Each tenant's data is isolated by including `tenant_id` in every query:

```python
from app.db.tenant import TenantDatabase

# TenantDatabase stores tenant_id and applies it in queries
tenant_db = TenantDatabase(tenant_id, db_manager=shared_db)
projects = await tenant_db.list_projects()
```

### Automatic Tenant Context

The middleware automatically sets tenant context from JWT:

```python
@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    if token := request.headers.get("authorization"):
        tenant_id = decode_jwt(token)["tenant_id"]
        request.state.tenant_id = tenant_id
    return await call_next(request)
```

### Cross-Tenant Admin Access

Admin endpoints can query across all tenants:

```python
async def get_all_tenants_usage(db: AdminDatabase):
    return await db.fetch_all(
        "SELECT tenant_id, COUNT(*) as projects FROM {{tables.projects}} GROUP BY tenant_id"
    )
```

## Testing

Run tests:
```bash
pytest
```

## Production Considerations

1. **Connection Pooling** - Use separate pools for admin vs tenant connections
2. **Data Migrations** - Handle schema changes across all tenant data
3. **Backup Strategy** - Per-tenant or full database backups
4. **Performance** - Index tenant_id columns for efficient filtering
5. **Security** - Validate tenant context on every request
