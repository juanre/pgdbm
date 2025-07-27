"""Database tests."""

from datetime import datetime

import pytest

from app.db import TodoDatabase, TodoNotFoundError


class TestTodoDatabase:
    """Test database operations."""

    async def test_create_todo(self, todo_db: TodoDatabase):
        """Test creating a todo."""
        todo = await todo_db.create_todo(title="Test Todo", description="Test Description")

        assert todo["title"] == "Test Todo"
        assert todo["description"] == "Test Description"
        assert todo["completed"] is False
        assert todo["id"] is not None
        assert isinstance(todo["created_at"], datetime)

    async def test_create_todo_minimal(self, todo_db: TodoDatabase):
        """Test creating a todo with minimal data."""
        todo = await todo_db.create_todo(title="Minimal Todo")

        assert todo["title"] == "Minimal Todo"
        assert todo["description"] is None
        assert todo["completed"] is False

    async def test_get_todo(self, todo_db: TodoDatabase):
        """Test getting a todo by ID."""
        # Create a todo
        created = await todo_db.create_todo(title="Get Test")

        # Get it back
        todo = await todo_db.get_todo(created["id"])

        assert todo["id"] == created["id"]
        assert todo["title"] == "Get Test"

    async def test_get_nonexistent_todo(self, todo_db: TodoDatabase):
        """Test getting a todo that doesn't exist."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(TodoNotFoundError) as exc_info:
            await todo_db.get_todo(fake_id)

        assert exc_info.value.todo_id == fake_id

    async def test_list_todos(self, todo_db_with_data: TodoDatabase):
        """Test listing todos."""
        todos = await todo_db_with_data.list_todos()

        assert len(todos) == 3
        # Should be ordered by created_at DESC
        assert todos[0]["created_at"] >= todos[1]["created_at"]

    async def test_list_todos_filtered(self, todo_db_with_data: TodoDatabase):
        """Test listing todos with filtering."""
        # Get completed todos
        completed = await todo_db_with_data.list_todos(completed=True)
        assert len(completed) == 1
        assert all(todo["completed"] for todo in completed)

        # Get pending todos
        pending = await todo_db_with_data.list_todos(completed=False)
        assert len(pending) == 2
        assert all(not todo["completed"] for todo in pending)

    async def test_list_todos_pagination(self, todo_db_with_data: TodoDatabase):
        """Test listing todos with pagination."""
        # First page
        page1 = await todo_db_with_data.list_todos(limit=2, offset=0)
        assert len(page1) == 2

        # Second page
        page2 = await todo_db_with_data.list_todos(limit=2, offset=2)
        assert len(page2) == 1

        # Ensure different todos
        page1_ids = {todo["id"] for todo in page1}
        page2_ids = {todo["id"] for todo in page2}
        assert not page1_ids.intersection(page2_ids)

    async def test_count_todos(self, todo_db_with_data: TodoDatabase):
        """Test counting todos."""
        total = await todo_db_with_data.count_todos()
        assert total == 3

        completed = await todo_db_with_data.count_todos(completed=True)
        assert completed == 1

        pending = await todo_db_with_data.count_todos(completed=False)
        assert pending == 2

    async def test_update_todo(self, todo_db: TodoDatabase):
        """Test updating a todo."""
        # Create a todo
        todo = await todo_db.create_todo(title="Original")

        # Update it
        updated = await todo_db.update_todo(
            todo["id"], title="Updated", description="New description"
        )

        assert updated["title"] == "Updated"
        assert updated["description"] == "New description"
        assert updated["updated_at"] > todo["updated_at"]

    async def test_update_todo_partial(self, todo_db: TodoDatabase):
        """Test partial update of a todo."""
        # Create a todo
        todo = await todo_db.create_todo(title="Original", description="Original description")

        # Update only title
        updated = await todo_db.update_todo(todo["id"], title="Updated")

        assert updated["title"] == "Updated"
        assert updated["description"] == "Original description"

    async def test_complete_todo(self, todo_db: TodoDatabase):
        """Test completing a todo."""
        # Create a todo
        todo = await todo_db.create_todo(title="To Complete")
        assert todo["completed"] is False
        assert todo["completed_at"] is None

        # Complete it
        completed = await todo_db.complete_todo(todo["id"])

        assert completed["completed"] is True
        assert completed["completed_at"] is not None
        assert isinstance(completed["completed_at"], datetime)

    async def test_delete_todo(self, todo_db: TodoDatabase):
        """Test deleting a todo."""
        # Create a todo
        todo = await todo_db.create_todo(title="To Delete")

        # Delete it
        await todo_db.delete_todo(todo["id"])

        # Verify it's gone
        with pytest.raises(TodoNotFoundError):
            await todo_db.get_todo(todo["id"])

    async def test_delete_nonexistent_todo(self, todo_db: TodoDatabase):
        """Test deleting a todo that doesn't exist."""
        fake_id = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(TodoNotFoundError):
            await todo_db.delete_todo(fake_id)

    async def test_health_check(self, todo_db: TodoDatabase):
        """Test health check."""
        health = await todo_db.health_check()

        assert health["status"] == "healthy"
        assert health["database"] == "connected"
        assert "pool" in health
        assert "todos" in health
        assert health["todos"]["total"] >= 0
