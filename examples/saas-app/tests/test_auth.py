"""Test authentication endpoints."""

import pytest
from httpx import AsyncClient

from app.db.admin import AdminDatabase


@pytest.mark.asyncio
async def test_user_registration(client: AsyncClient, test_tenant):
    """Test user registration within a tenant."""
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "newuser@test.com",
            "password": "newpass123",
            "tenant_id": str(test_tenant["tenant"].id),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "newuser@test.com"
    assert "api_key" in data
    assert data["tenant_id"] == str(test_tenant["tenant"].id)


@pytest.mark.asyncio
async def test_user_login(client: AsyncClient, test_tenant):
    """Test user login."""
    response = await client.post(
        "/api/auth/login",
        json={"email": test_tenant["user"]["email"], "password": test_tenant["password"]},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_tenant["user"]["email"]
    assert "api_key" in data


@pytest.mark.asyncio
async def test_invalid_login(client: AsyncClient, admin_db: AdminDatabase):
    """Test login with invalid credentials."""
    response = await client.post(
        "/api/auth/login", json={"email": "nonexistent@test.com", "password": "wrongpass"}
    )

    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]


@pytest.mark.asyncio
async def test_get_current_user(client: AsyncClient, auth_headers):
    """Test getting current user info."""
    response = await client.get("/api/auth/me", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "admin@test.com"


@pytest.mark.asyncio
async def test_api_key_regeneration(client: AsyncClient, test_tenant):
    """Test that API key is regenerated on each login."""
    # First login
    response1 = await client.post(
        "/api/auth/login",
        json={"email": test_tenant["user"]["email"], "password": test_tenant["password"]},
    )
    assert response1.status_code == 200
    api_key1 = response1.json()["api_key"]

    # Second login
    response2 = await client.post(
        "/api/auth/login",
        json={"email": test_tenant["user"]["email"], "password": test_tenant["password"]},
    )
    assert response2.status_code == 200
    api_key2 = response2.json()["api_key"]

    # API keys should be different
    assert api_key1 != api_key2


@pytest.mark.asyncio
async def test_tenant_user_limit(client: AsyncClient, test_tenant, admin_db):
    """Test that tenant user limits are enforced."""
    # Update tenant to have max 2 users (already has 1)
    await admin_db.execute(
        "UPDATE tenants SET max_users = 2 WHERE id = $1", test_tenant["tenant"].id
    )

    # First new user should succeed
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "user2@test.com",
            "password": "pass1234",  # Minimum 8 characters
            "tenant_id": str(test_tenant["tenant"].id),
        },
    )
    assert response.status_code == 200

    # Second new user should fail
    response = await client.post(
        "/api/auth/register",
        json={
            "email": "user3@test.com",
            "password": "pass1234",  # Minimum 8 characters
            "tenant_id": str(test_tenant["tenant"].id),
        },
    )
    assert response.status_code == 400
    assert "limit reached" in response.json()["detail"]
