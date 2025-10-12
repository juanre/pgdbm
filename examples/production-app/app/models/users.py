"""User models."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class UserBase(BaseModel):
    """Base user model."""

    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    is_active: bool = True


class UserCreate(UserBase):
    """Model for creating a user."""

    password: str = Field(..., min_length=8)


class UserUpdate(BaseModel):
    """Model for updating a user."""

    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8)


class UserInDB(UserBase):
    """User model as stored in database."""

    id: int
    created_at: datetime
    updated_at: datetime
    hashed_password: str

    class Config:
        from_attributes = True


class UserResponse(UserBase):
    """User model for API responses."""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
