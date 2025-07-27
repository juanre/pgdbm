"""Authentication endpoints."""

import secrets

from fastapi import APIRouter, HTTPException, Request
from passlib.context import CryptContext

from ..models.user import User, UserCreate, UserLogin, UserWithApiKey

router = APIRouter(prefix="/api/auth", tags=["Authentication"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """Hash a password."""
    return pwd_context.hash(password)


def generate_api_key() -> str:
    """Generate a secure API key."""
    return secrets.token_urlsafe(32)


@router.post("/register", response_model=UserWithApiKey)
async def register(request: Request, user_data: UserCreate):
    """Register a new user."""
    db = request.app.state.admin_db

    # Check if user exists
    existing = await db.get_user_by_email(user_data.email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Validate tenant if provided
    if user_data.tenant_id:
        tenant = await db.get_tenant(user_data.tenant_id)
        if not tenant:
            raise HTTPException(status_code=404, detail="Tenant not found")

        # Check tenant user limit
        user_count = await db.fetch_one(
            "SELECT COUNT(*) as count FROM users WHERE tenant_id = $1", user_data.tenant_id
        )
        if user_count and user_count["count"] >= tenant.max_users:
            raise HTTPException(status_code=400, detail="Tenant user limit reached")

    # Create user
    password_hash = get_password_hash(user_data.password)
    user_dict = await db.create_user(
        email=user_data.email,
        password_hash=password_hash,
        tenant_id=user_data.tenant_id,
        is_admin=False,  # Regular users are not admins by default
    )

    if not user_dict:
        raise HTTPException(status_code=500, detail="Failed to create user")

    # Generate API key
    api_key = generate_api_key()
    await db.execute("UPDATE users SET api_key = $1 WHERE id = $2", api_key, user_dict["id"])

    # Log audit event
    await db.log_audit(
        action="user.registered",
        user_id=user_dict["id"],
        tenant_id=user_data.tenant_id,
        metadata={"email": user_dict["email"]},
    )

    user_dict["api_key"] = api_key
    return UserWithApiKey(**user_dict)


@router.post("/login", response_model=UserWithApiKey)
async def login(request: Request, credentials: UserLogin):
    """Login a user."""
    db = request.app.state.admin_db

    # Get user
    user_dict = await db.get_user_by_email(credentials.email)
    if not user_dict:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Verify password
    if not verify_password(credentials.password, user_dict["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Check if tenant is active
    if user_dict["tenant_id"]:
        tenant = await db.get_tenant(user_dict["tenant_id"])
        if not tenant or tenant.status != "active":
            raise HTTPException(status_code=403, detail="Tenant account is not active")

    # Generate new API key on login
    api_key = generate_api_key()
    await db.execute(
        "UPDATE users SET api_key = $1, last_login_at = NOW() WHERE id = $2",
        api_key,
        user_dict["id"],
    )

    # Log audit event
    await db.log_audit(
        action="user.login",
        user_id=user_dict["id"],
        tenant_id=user_dict["tenant_id"],
        metadata={"email": user_dict["email"]},
    )

    user_dict["api_key"] = api_key
    return UserWithApiKey(**user_dict)


@router.get("/me", response_model=User)
async def get_current_user(request: Request):
    """Get current user information."""
    if not hasattr(request.state, "user"):
        raise HTTPException(status_code=401, detail="Not authenticated")

    return request.state.user
