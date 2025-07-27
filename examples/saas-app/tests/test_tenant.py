"""Test tenant management."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_tenant_signup(client: AsyncClient, admin_db):
    """Test tenant signup flow."""
    response = await client.post(
        "/api/tenants/signup",
        json={
            "name": "New Company",
            "slug": "new-company",
            "email": "admin@newcompany.com",
            "plan": "starter",
            "admin_password": "securepass123",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "api_key" in data
    assert data["email"] == "admin@newcompany.com"


@pytest.mark.asyncio
async def test_duplicate_tenant_slug(client: AsyncClient, test_tenant):
    """Test that duplicate tenant slugs are rejected."""
    response = await client.post(
        "/api/tenants/signup",
        json={
            "name": "Another Company",
            "slug": test_tenant["tenant"].slug,  # Duplicate slug
            "email": "admin@another.com",
            "plan": "free",
            "admin_password": "password123",
        },
    )

    assert response.status_code == 400
    assert "already taken" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_current_tenant(client: AsyncClient, auth_headers):
    """Test getting current tenant info."""
    response = await client.get("/api/tenants/current", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Test Company"
    assert "user_count" in data
    assert "project_count" in data


@pytest.mark.asyncio
async def test_list_tenants_admin_only(client: AsyncClient, auth_headers, admin_headers):
    """Test that only admins can list all tenants."""
    # Regular user should fail
    response = await client.get("/api/tenants/", headers=auth_headers)
    assert response.status_code == 403

    # Admin should succeed
    response = await client.get("/api/tenants/", headers=admin_headers)
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_update_tenant(client: AsyncClient, test_tenant, admin_headers):
    """Test updating tenant details."""
    response = await client.patch(
        f"/api/tenants/{test_tenant['tenant'].id}",
        headers=admin_headers,
        json={"name": "Updated Company Name", "plan": "enterprise"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Company Name"
    assert data["plan"] == "enterprise"


@pytest.mark.asyncio
async def test_suspend_tenant(client: AsyncClient, test_tenant, admin_headers):
    """Test suspending a tenant."""
    response = await client.post(
        f"/api/tenants/{test_tenant['tenant'].id}/suspend",
        headers=admin_headers,
        params={"reason": "Non-payment"},
    )

    assert response.status_code == 200

    # Verify tenant is suspended
    response = await client.get(f"/api/tenants/{test_tenant['tenant'].id}", headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "suspended"
