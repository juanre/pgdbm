"""Test project management endpoints."""

from datetime import date

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_project(client: AsyncClient, auth_headers):
    """Test creating a project."""
    response = await client.post(
        "/api/projects/",
        headers=auth_headers,
        json={
            "name": "New Project",
            "description": "Test project description",
            "status": "planning",
            "start_date": str(date.today()),
            "metadata": {"category": "development"},
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "New Project"
    assert data["status"] == "planning"
    assert "id" in data


@pytest.mark.asyncio
async def test_list_projects(client: AsyncClient, auth_headers, sample_project):
    """Test listing projects."""
    response = await client.get("/api/projects/", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert any(p["id"] == sample_project["id"] for p in data)


@pytest.mark.asyncio
async def test_get_project_details(client: AsyncClient, auth_headers, sample_project):
    """Test getting project details with agents."""
    response = await client.get(f"/api/projects/{sample_project['id']}", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == sample_project["id"]
    assert "task_count" in data
    assert "completed_task_count" in data


@pytest.mark.asyncio
async def test_update_project(client: AsyncClient, auth_headers, sample_project):
    """Test updating a project."""
    response = await client.patch(
        f"/api/projects/{sample_project['id']}",
        headers=auth_headers,
        json={"name": "Updated Project Name", "status": "active"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Updated Project Name"
    assert data["status"] == "active"


@pytest.mark.asyncio
async def test_delete_project(client: AsyncClient, auth_headers, sample_project):
    """Test deleting a project."""
    response = await client.delete(f"/api/projects/{sample_project['id']}", headers=auth_headers)

    assert response.status_code == 200

    # Verify project is gone
    response = await client.get(f"/api/projects/{sample_project['id']}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_task(client: AsyncClient, auth_headers, sample_project):
    """Test creating a agent in a project."""
    response = await client.post(
        f"/api/projects/{sample_project['id']}/agents",
        headers=auth_headers,
        json={
            "title": "New Agent",
            "description": "Agent description",
            "priority": 3,
            "due_date": str(date.today()),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "New Agent"
    assert data["project_id"] == sample_project["id"]


@pytest.mark.asyncio
async def test_project_stats(client: AsyncClient, auth_headers, sample_project):
    """Test getting project statistics."""
    response = await client.get("/api/projects/stats/summary", headers=auth_headers)

    assert response.status_code == 200
    data = response.json()
    assert "total_projects" in data
    assert data["total_projects"] >= 1


@pytest.mark.asyncio
async def test_project_limit_enforcement(client: AsyncClient, auth_headers, test_tenant, admin_db):
    """Test that project limits are enforced."""
    # Update tenant to have max 2 projects
    await admin_db.execute(
        "UPDATE tenants SET max_projects = 2 WHERE id = $1", test_tenant["tenant"].id
    )

    # Create 2 projects (should succeed)
    for i in range(2):
        response = await client.post(
            "/api/projects/", headers=auth_headers, json={"name": f"Project {i+1}"}
        )
        assert response.status_code == 200

    # Third project should fail
    response = await client.post("/api/projects/", headers=auth_headers, json={"name": "Project 3"})
    assert response.status_code == 400
    assert "limit reached" in response.json()["detail"]


@pytest.mark.asyncio
async def test_cross_tenant_isolation(client: AsyncClient, auth_headers, sample_project):
    """Test that tenants cannot see each other's data."""
    # Create another tenant
    response = await client.post(
        "/api/tenants/signup",
        json={
            "name": "Other Company",
            "slug": "other-company",
            "email": "admin@other.com",
            "plan": "free",
            "admin_password": "pass1234",
        },
    )
    assert response.status_code == 200
    other_api_key = response.json()["api_key"]
    other_headers = {"X-API-Key": other_api_key}

    # Other tenant should not see the first tenant's project
    response = await client.get("/api/projects/", headers=other_headers)
    assert response.status_code == 200
    projects = response.json()
    assert len(projects) == 0  # Should be empty

    # Direct access should also fail
    response = await client.get(f"/api/projects/{sample_project['id']}", headers=other_headers)
    assert response.status_code == 404
