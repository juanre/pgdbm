"""Test configuration and fixtures for SaaS app."""

import os
from collections.abc import AsyncGenerator
from uuid import uuid4

import pytest
from httpx import AsyncClient

# Set test environment
os.environ["APP_ENV"] = "testing"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://test:test@localhost/test_saas"
)

from app.api.auth import get_password_hash
from app.db.admin import AdminDatabase
from app.db.tenant import TenantDatabase
from app.main import app
from app.models.tenant import TenantCreate

# Import base fixtures from pgdbm
from pgdbm.fixtures.conftest import test_db  # noqa: F401 - used by pytest


@pytest.fixture
async def client(test_db) -> AsyncGenerator[AsyncClient, None]:  # noqa: F811
    """Create test client."""
    # Set up app state manually for tests
    app.state.db = test_db
    app.state.admin_db = AdminDatabase(test_db)

    from httpx import ASGITransport

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def admin_db(test_db) -> AdminDatabase:  # noqa: F811
    """Get admin database wrapper."""
    admin = AdminDatabase(test_db)
    # Run the unified schema migrations
    migration_manager = await admin.get_migration_manager()
    await migration_manager.apply_pending_migrations()
    return admin


@pytest.fixture
async def test_tenant(admin_db: AdminDatabase) -> dict:
    """Create a test tenant."""
    tenant_data = TenantCreate(
        name="Test Company",
        slug=f"test-{uuid4().hex[:8]}",
        email="admin@test.com",
        plan="pro",
        max_projects=50,
        max_users=10,
    )

    tenant = await admin_db.create_tenant(tenant_data)

    # Create admin user for tenant
    user = await admin_db.create_user(
        email=tenant_data.email,
        password_hash=get_password_hash("testpass123"),
        tenant_id=tenant.id,
        display_name="Test Admin",
        role="admin",
    )

    return {"tenant": tenant, "user": user, "password": "testpass123"}


@pytest.fixture
async def auth_headers(client: AsyncClient, test_tenant: dict) -> dict:
    """Get authentication headers for test tenant."""
    response = await client.post(
        "/api/auth/login",
        json={"email": test_tenant["user"]["email"], "password": test_tenant["password"]},
    )

    assert response.status_code == 200
    api_key = response.json()["api_key"]

    return {"X-API-Key": api_key}


@pytest.fixture
async def admin_user(admin_db: AdminDatabase) -> dict:
    """Create a global admin user."""
    user = await admin_db.create_user(
        email="admin@system.com", password_hash=get_password_hash("adminpass123"), is_admin=True
    )

    return {"user": user, "password": "adminpass123"}


@pytest.fixture
async def admin_headers(client: AsyncClient, admin_user: dict) -> dict:
    """Get authentication headers for admin user."""
    response = await client.post(
        "/api/auth/login",
        json={"email": admin_user["user"]["email"], "password": admin_user["password"]},
    )

    assert response.status_code == 200
    api_key = response.json()["api_key"]

    return {"X-API-Key": api_key}


@pytest.fixture
async def tenant_db(test_tenant: dict, admin_db: AdminDatabase) -> TenantDatabase:
    """Get tenant database wrapper."""
    return TenantDatabase(str(test_tenant["tenant"].id), admin_db.db)


@pytest.fixture
async def sample_project(client: AsyncClient, auth_headers: dict) -> dict:
    """Create a sample project."""
    response = await client.post(
        "/api/projects/",
        headers=auth_headers,
        json={"name": "Test Project", "description": "A test project", "status": "active"},
    )

    assert response.status_code == 200
    return response.json()
