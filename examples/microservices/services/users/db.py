"""Database operations for user service."""

from typing import Any, Optional
from uuid import UUID

from passlib.context import CryptContext

from shared.database import ServiceDatabase
from shared.models import User, UserCreate

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class UserDatabase(ServiceDatabase):
    """User service database operations."""

    def __init__(self):
        super().__init__("user-service", "users")

    async def create_user(self, user: UserCreate) -> User:
        """Create a new user."""
        # Hash password
        password_hash = pwd_context.hash(user.password)

        result = await self.fetch_one(
            """
            INSERT INTO {{tables.users}} (email, name, password_hash)
            VALUES ($1, $2, $3)
            RETURNING *
        """,
            user.email,
            user.name,
            password_hash,
        )

        if not result:
            raise ValueError("Failed to create user")

        return User(**result)

    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        result = await self.fetch_one("SELECT * FROM {{tables.users}} WHERE email = $1", email)

        return User(**result) if result else None

    async def get_user_by_id(self, user_id: UUID) -> Optional[User]:
        """Get user by ID."""
        result = await self.fetch_one("SELECT * FROM {{tables.users}} WHERE id = $1", user_id)

        return User(**result) if result else None

    async def verify_password(self, email: str, password: str) -> Optional[User]:
        """Verify user password."""
        result = await self.fetch_one("SELECT * FROM {{tables.users}} WHERE email = $1", email)

        if not result:
            return None

        if not pwd_context.verify(password, result["password_hash"]):
            return None

        return User(**result)

    async def update_user(self, user_id: UUID, updates: dict[str, Any]) -> Optional[User]:
        """Update user information."""
        if not updates:
            return await self.get_user_by_id(user_id)

        # Build update query
        set_clauses = []
        params = []
        param_count = 0

        for field, value in updates.items():
            if field not in ["email", "name", "is_active"]:
                continue
            param_count += 1
            set_clauses.append(f"{field} = ${param_count}")
            params.append(value)

        if not set_clauses:
            return await self.get_user_by_id(user_id)

        param_count += 1
        params.append(user_id)

        query = f"""
            UPDATE {{tables.users}}
            SET {', '.join(set_clauses)}, updated_at = NOW()
            WHERE id = ${param_count}
            RETURNING *
        """

        result = await self.fetch_one(query, *params)
        return User(**result) if result else None

    async def delete_user(self, user_id: UUID) -> bool:
        """Delete a user (soft delete)."""
        result = await self.fetch_one(
            """
            UPDATE {{tables.users}}
            SET is_active = FALSE, updated_at = NOW()
            WHERE id = $1
            RETURNING id
        """,
            user_id,
        )

        return result is not None

    async def list_users(
        self, limit: int = 10, offset: int = 0, is_active: Optional[bool] = None
    ) -> list[User]:
        """List users with pagination."""
        query = "SELECT * FROM {{tables.users}} WHERE 1=1"
        params = []
        param_count = 0

        if is_active is not None:
            param_count += 1
            query += f" AND is_active = ${param_count}"
            params.append(is_active)

        query += " ORDER BY created_at DESC"

        param_count += 1
        query += f" LIMIT ${param_count}"
        params.append(limit)

        param_count += 1
        query += f" OFFSET ${param_count}"
        params.append(offset)

        results = await self.fetch_all(query, *params)
        return [User(**row) for row in results]
