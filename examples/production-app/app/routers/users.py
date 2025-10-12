"""User management endpoints."""

import hashlib
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.dependencies import UsersDB
from app.models.users import UserCreate, UserResponse, UserUpdate

router = APIRouter(prefix="/users")


def hash_password(password: str) -> str:
    """Hash password (use bcrypt in production)."""
    return hashlib.sha256(password.encode()).hexdigest()


@router.post("", response_model=UserResponse)
async def create_user(user: UserCreate, db: UsersDB):
    """Create a new user."""
    # Check if user exists
    existing = await db.fetch_one("SELECT id FROM {{tables.users}} WHERE email = $1", user.email)

    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create user
    result = await db.fetch_one(
        """
        INSERT INTO {{tables.users}} (email, full_name, hashed_password, is_active)
        VALUES ($1, $2, $3, $4)
        RETURNING id, email, full_name, is_active, created_at, updated_at
        """,
        user.email,
        user.full_name,
        hash_password(user.password),
        user.is_active,
    )

    return UserResponse(**dict(result))


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: UsersDB):
    """Get a user by ID."""
    user = await db.fetch_one(
        """
        SELECT id, email, full_name, is_active, created_at, updated_at
        FROM {{tables.users}}
        WHERE id = $1
        """,
        user_id,
    )

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(**dict(user))


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, update: UserUpdate, db: UsersDB):
    """Update a user."""
    # Build update query dynamically
    updates = []
    params = []
    param_count = 1

    if update.email is not None:
        updates.append(f"email = ${param_count}")
        params.append(update.email)
        param_count += 1

    if update.full_name is not None:
        updates.append(f"full_name = ${param_count}")
        params.append(update.full_name)
        param_count += 1

    if update.is_active is not None:
        updates.append(f"is_active = ${param_count}")
        params.append(update.is_active)
        param_count += 1

    if update.password is not None:
        updates.append(f"hashed_password = ${param_count}")
        params.append(hash_password(update.password))
        param_count += 1

    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")

    updates.append("updated_at = NOW()")
    params.append(user_id)

    query = f"""
        UPDATE {{{{tables.users}}}}
        SET {', '.join(updates)}
        WHERE id = ${param_count}
        RETURNING id, email, full_name, is_active, created_at, updated_at
    """

    user = await db.fetch_one(query, *params)

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserResponse(**dict(user))


@router.delete("/{user_id}")
async def delete_user(user_id: int, db: UsersDB):
    """Delete a user."""
    result = await db.execute("DELETE FROM {{tables.users}} WHERE id = $1", user_id)

    if result == "DELETE 0":
        raise HTTPException(status_code=404, detail="User not found")

    return {"message": "User deleted successfully"}


@router.get("", response_model=list[UserResponse])
async def list_users(
    db: UsersDB,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    is_active: Optional[bool] = None,
):
    """List users with pagination."""
    query = """
        SELECT id, email, full_name, is_active, created_at, updated_at
        FROM {{tables.users}}
    """
    params = []

    if is_active is not None:
        query += " WHERE is_active = $1"
        params.append(is_active)

    query += f" ORDER BY created_at DESC LIMIT {limit} OFFSET {skip}"

    users = await db.fetch_all(query, *params)

    return [UserResponse(**dict(user)) for user in users]
