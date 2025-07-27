"""User service API endpoints."""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from shared.events import EventTypes, event_bus
from shared.models import MessageResponse, User, UserCreate, UserWithToken

router = APIRouter(prefix="/users", tags=["Users"])
security = HTTPBearer(auto_error=False)

# JWT configuration
JWT_SECRET = "your-secret-key"  # In production, use environment variable
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


def create_access_token(user_id: str) -> str:
    """Create JWT access token."""
    expire = datetime.utcnow() + timedelta(hours=JWT_EXPIRATION_HOURS)
    payload = {"sub": user_id, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


async def get_current_user(
    request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> User:
    """Get current user from JWT token."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        # Get user from database
        db = request.app.state.db
        user = await db.get_user_by_id(UUID(user_id))
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        return user

    except JWTError as e:
        raise HTTPException(status_code=401, detail="Invalid token") from e


@router.post("/register", response_model=UserWithToken)
async def register_user(request: Request, user_data: UserCreate):
    """Register a new user."""
    db = request.app.state.db

    # Check if email already exists
    existing = await db.get_user_by_email(user_data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create user
    user = await db.create_user(user_data)

    # Create access token
    token = create_access_token(str(user.id))

    # Publish user created event
    await event_bus.publish(
        EventTypes.USER_CREATED,
        {"user_id": str(user.id), "email": user.email, "name": user.name},
        aggregate_id=user.id,
        aggregate_type="user",
    )

    return UserWithToken(**user.model_dump(), access_token=token)


@router.post("/login", response_model=UserWithToken)
async def login_user(request: Request, credentials: dict):
    """Login user with email and password."""
    db = request.app.state.db

    email = credentials.get("email")
    password = credentials.get("password")

    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")

    # Verify credentials
    user = await db.verify_password(email, password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account deactivated")

    # Create access token
    token = create_access_token(str(user.id))

    return UserWithToken(**user.model_dump(), access_token=token)


@router.get("/me", response_model=User)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current user information."""
    return current_user


@router.get("/{user_id}", response_model=User)
async def get_user(request: Request, user_id: UUID):
    """Get user by ID."""
    db = request.app.state.db

    user = await db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return user


@router.put("/me", response_model=User)
async def update_current_user(
    request: Request, updates: dict, current_user: User = Depends(get_current_user)
):
    """Update current user information."""
    db = request.app.state.db

    # Only allow updating name and email
    allowed_updates = {k: v for k, v in updates.items() if k in ["name", "email"]}

    if "email" in allowed_updates:
        # Check if new email is already taken
        existing = await db.get_user_by_email(allowed_updates["email"])
        if existing and existing.id != current_user.id:
            raise HTTPException(status_code=400, detail="Email already taken")

    # Update user
    updated_user = await db.update_user(current_user.id, allowed_updates)
    if not updated_user:
        raise HTTPException(status_code=500, detail="Failed to update user")

    # Publish user updated event
    await event_bus.publish(
        EventTypes.USER_UPDATED,
        {"user_id": str(updated_user.id), "updates": allowed_updates},
        aggregate_id=updated_user.id,
        aggregate_type="user",
    )

    return updated_user


@router.delete("/me", response_model=MessageResponse)
async def delete_current_user(request: Request, current_user: User = Depends(get_current_user)):
    """Delete current user account."""
    db = request.app.state.db

    # Soft delete user
    success = await db.delete_user(current_user.id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete user")

    # Publish user deleted event
    await event_bus.publish(
        EventTypes.USER_DELETED,
        {"user_id": str(current_user.id), "email": current_user.email},
        aggregate_id=current_user.id,
        aggregate_type="user",
    )

    return MessageResponse(message="User account deleted successfully")


@router.get("/", response_model=list[User])
async def list_users(
    request: Request, limit: int = 10, offset: int = 0, is_active: Optional[bool] = None
):
    """List users (admin endpoint in real app)."""
    db = request.app.state.db

    users = await db.list_users(limit=limit, offset=offset, is_active=is_active)
    return users
