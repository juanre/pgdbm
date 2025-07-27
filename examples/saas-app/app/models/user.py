"""User models."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class UserBase(BaseModel):
    """Base user model."""

    email: EmailStr


class UserCreate(UserBase):
    """Model for creating a user."""

    password: str = Field(..., min_length=8)
    tenant_id: Optional[UUID] = None


class UserLogin(BaseModel):
    """Model for user login."""

    email: EmailStr
    password: str


class User(UserBase):
    """Complete user model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: Optional[UUID] = None
    api_key: Optional[str] = None
    is_admin: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


class UserWithApiKey(User):
    """User model with API key."""

    api_key: str
