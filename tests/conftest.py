"""
Pytest configuration and fixtures for pgdbm-utils tests.
"""

import asyncio

import pytest

# Import all fixtures from the library
from pgdbm.fixtures.conftest import *  # noqa: F401, F403


# For backward compatibility, also keep test_db_manager as alias
@pytest.fixture
async def test_db_manager(test_db):  # noqa: F811
    """Alias for test_db fixture for backward compatibility."""
    yield test_db


# Keep the event loop fixture as it was
@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# Keep sample_tables but use the correct fixture
@pytest.fixture
async def sample_tables(test_db):
    """Create sample tables for testing."""
    # Create users table
    await test_db.execute(
        """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            email VARCHAR(255) UNIQUE NOT NULL,
            full_name VARCHAR(255),
            is_active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Create projects table
    await test_db.execute(
        """
        CREATE TABLE projects (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            owner_id INTEGER REFERENCES users(id),
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Create agents table
    await test_db.execute(
        """
        CREATE TABLE agents (
            id SERIAL PRIMARY KEY,
            project_id INTEGER REFERENCES projects(id),
            title VARCHAR(255) NOT NULL,
            status VARCHAR(50) DEFAULT 'pending',
            assigned_to INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Add some sample data
    await test_db.execute(
        """
        INSERT INTO users (email, full_name) VALUES
        ('alice@example.com', 'Alice Smith'),
        ('bob@example.com', 'Bob Jones'),
        ('charlie@example.com', 'Charlie Brown')
    """
    )

    yield test_db
