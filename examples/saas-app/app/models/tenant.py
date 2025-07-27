"""Tenant models."""

import re
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class TenantPlan(str, Enum):
    """Tenant subscription plans."""

    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class TenantStatus(str, Enum):
    """Tenant account status."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class TenantBase(BaseModel):
    """Base tenant model."""

    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    plan: TenantPlan = TenantPlan.FREE
    metadata: Optional[dict[str, Any]] = Field(default_factory=dict)


class TenantCreate(TenantBase):
    """Model for creating a tenant."""

    slug: str = Field(..., min_length=3, max_length=63)
    max_projects: Optional[int] = Field(default=10, ge=1)
    max_users: Optional[int] = Field(default=5, ge=1)

    @field_validator("slug")
    def validate_slug(cls, v):
        """Validate slug format."""
        if not re.match(r"^[a-z0-9-]+$", v):
            raise ValueError("Slug must contain only lowercase letters, numbers, and hyphens")
        if v.startswith("-") or v.endswith("-"):
            raise ValueError("Slug cannot start or end with a hyphen")
        return v


class TenantSignup(TenantCreate):
    """Model for tenant signup with admin password."""

    admin_password: str = Field(..., min_length=8)


class TenantUpdate(BaseModel):
    """Model for updating a tenant."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    plan: Optional[TenantPlan] = None
    status: Optional[TenantStatus] = None
    max_projects: Optional[int] = Field(None, ge=1)
    max_users: Optional[int] = Field(None, ge=1)
    metadata: Optional[dict[str, Any]] = None
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None


class Tenant(TenantBase):
    """Complete tenant model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    status: TenantStatus
    max_projects: int
    max_users: int

    # Billing
    stripe_customer_id: Optional[str] = None
    stripe_subscription_id: Optional[str] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime
    suspended_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None


class TenantWithUsage(Tenant):
    """Tenant model with usage statistics."""

    user_count: int = 0
    project_count: int = 0
    task_count: int = 0
    storage_mb: float = 0.0
