"""Test configuration and fixtures."""

import os

import pytest
import pytest_asyncio

from pgdbm import AsyncMigrationManager
from pgdbm.fixtures.conftest import test_db_factory  # noqa: F401 - used by pytest

# Set testing environment
os.environ["APP_ENV"] = "testing"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql://test:test@localhost/test_todo"
)

from app.db import TodoDatabase


@pytest_asyncio.fixture
async def todo_db(test_db_factory):  # noqa: F811
    """Create todo database with schema and migrations."""
    # Create test database with isolated schema
    db_manager = await test_db_factory.create_db(suffix="todo", schema="test_todo")

    # Initialize todo wrapper
    todo_db = TodoDatabase.from_manager(db_manager)

    # Apply migrations
    migrations = AsyncMigrationManager(db_manager, migrations_path="./migrations")
    await migrations.apply_pending_migrations()

    yield todo_db
    # Cleanup is automatic


@pytest_asyncio.fixture
async def todo_db_with_data(todo_db):
    """Todo database with sample data."""
    # Create sample todos
    await todo_db.create_todo("Buy groceries", "Milk, eggs, bread")
    await todo_db.create_todo("Write documentation", "Update README")
    await todo_db.create_todo("Review PRs", None)

    # Complete one todo
    todos = await todo_db.list_todos()
    await todo_db.complete_todo(todos[0]["id"])

    yield todo_db


@pytest.fixture
def test_app(todo_db):
    """Create test FastAPI application."""
    from fastapi.testclient import TestClient

    from app.main import app

    # Override database
    app.state.db = todo_db

    return TestClient(app)


@pytest_asyncio.fixture
async def async_test_app(todo_db):
    """Create async test client."""
    from httpx import ASGITransport, AsyncClient

    from app.main import app

    # Override database
    app.state.db = todo_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
