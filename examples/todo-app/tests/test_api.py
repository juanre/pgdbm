"""API endpoint tests."""

from httpx import AsyncClient


class TestTodoAPI:
    """Test todo API endpoints."""

    async def test_create_todo(self, async_test_app: AsyncClient):
        """Test creating a todo via API."""
        response = await async_test_app.post(
            "/api/todos", json={"title": "API Test Todo", "description": "Created via API"}
        )

        assert response.status_code == 201
        data = response.json()
        assert data["title"] == "API Test Todo"
        assert data["description"] == "Created via API"
        assert data["completed"] is False
        assert "id" in data

    async def test_create_todo_validation(self, async_test_app: AsyncClient):
        """Test todo creation validation."""
        # Missing title
        response = await async_test_app.post("/api/todos", json={"description": "No title"})
        assert response.status_code == 422

        # Empty title
        response = await async_test_app.post(
            "/api/todos", json={"title": "", "description": "Empty title"}
        )
        assert response.status_code == 422

    async def test_get_todo(self, async_test_app: AsyncClient):
        """Test getting a todo via API."""
        # Create a todo first
        create_response = await async_test_app.post("/api/todos", json={"title": "Get Test"})
        todo_id = create_response.json()["id"]

        # Get it
        response = await async_test_app.get(f"/api/todos/{todo_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == todo_id
        assert data["title"] == "Get Test"

    async def test_get_nonexistent_todo(self, async_test_app: AsyncClient):
        """Test getting a todo that doesn't exist."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await async_test_app.get(f"/api/todos/{fake_id}")

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]

    async def test_list_todos(self, async_test_app: AsyncClient):
        """Test listing todos."""
        # Create some todos
        for i in range(3):
            await async_test_app.post("/api/todos", json={"title": f"Todo {i}"})

        # List them
        response = await async_test_app.get("/api/todos")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 3
        assert data["total"] == 3
        assert data["has_more"] is False

    async def test_list_todos_filtered(self, async_test_app: AsyncClient):
        """Test listing todos with filtering."""
        # Create todos
        todo1 = await async_test_app.post("/api/todos", json={"title": "Completed"})
        await async_test_app.post("/api/todos", json={"title": "Pending"})

        # Complete one
        await async_test_app.post(f"/api/todos/{todo1.json()['id']}/complete")

        # Get completed todos
        response = await async_test_app.get("/api/todos?completed=true")
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["completed"] is True

        # Get pending todos
        response = await async_test_app.get("/api/todos?completed=false")
        data = response.json()
        assert len(data["items"]) == 1
        assert data["items"][0]["completed"] is False

    async def test_list_todos_pagination(self, async_test_app: AsyncClient):
        """Test listing todos with pagination."""
        # Create 5 todos
        for i in range(5):
            await async_test_app.post("/api/todos", json={"title": f"Todo {i}"})

        # Get first page
        response = await async_test_app.get("/api/todos?limit=2&offset=0")
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 5
        assert data["has_more"] is True

        # Get last page
        response = await async_test_app.get("/api/todos?limit=2&offset=4")
        data = response.json()
        assert len(data["items"]) == 1
        assert data["has_more"] is False

    async def test_update_todo(self, async_test_app: AsyncClient):
        """Test updating a todo."""
        # Create a todo
        create_response = await async_test_app.post("/api/todos", json={"title": "Original"})
        todo_id = create_response.json()["id"]

        # Update it
        response = await async_test_app.put(
            f"/api/todos/{todo_id}",
            json={"title": "Updated", "description": "New description", "completed": True},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "Updated"
        assert data["description"] == "New description"
        assert data["completed"] is True

    async def test_complete_todo(self, async_test_app: AsyncClient):
        """Test completing a todo."""
        # Create a todo
        create_response = await async_test_app.post("/api/todos", json={"title": "To Complete"})
        todo_id = create_response.json()["id"]

        # Complete it
        response = await async_test_app.post(f"/api/todos/{todo_id}/complete")

        assert response.status_code == 200
        data = response.json()
        assert data["completed"] is True
        assert data["completed_at"] is not None

    async def test_delete_todo(self, async_test_app: AsyncClient):
        """Test deleting a todo."""
        # Create a todo
        create_response = await async_test_app.post("/api/todos", json={"title": "To Delete"})
        todo_id = create_response.json()["id"]

        # Delete it
        response = await async_test_app.delete(f"/api/todos/{todo_id}")
        assert response.status_code == 204

        # Verify it's gone
        response = await async_test_app.get(f"/api/todos/{todo_id}")
        assert response.status_code == 404


class TestHealthAPI:
    """Test health check endpoints."""

    async def test_health_check(self, async_test_app: AsyncClient):
        """Test basic health check."""
        response = await async_test_app.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    async def test_readiness_check(self, async_test_app: AsyncClient):
        """Test readiness check."""
        response = await async_test_app.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["database"] == "connected"
        assert "pool" in data
        assert "todos" in data
