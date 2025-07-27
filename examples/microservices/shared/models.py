"""Shared data models across microservices."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# Enums
class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class NotificationType(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"


class NotificationStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


# User models
class UserBase(BaseModel):
    email: EmailStr
    name: str


class UserCreate(UserBase):
    password: str


class User(UserBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserWithToken(User):
    access_token: str
    token_type: str = "bearer"


# Product models
class ProductBase(BaseModel):
    sku: str
    name: str
    description: Optional[str] = None
    price: Decimal = Field(..., decimal_places=2)


class ProductCreate(ProductBase):
    stock_quantity: int = 0


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = Field(None, decimal_places=2)
    stock_quantity: Optional[int] = None
    is_active: Optional[bool] = None


class Product(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    stock_quantity: int
    reserved_quantity: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @property
    def available_quantity(self) -> int:
        return self.stock_quantity - self.reserved_quantity


# Order models
class OrderItemCreate(BaseModel):
    product_id: UUID
    quantity: int = Field(..., ge=1)


class OrderItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    order_id: UUID
    product_id: UUID
    quantity: int
    unit_price: Decimal
    total_price: Decimal
    created_at: datetime


class OrderCreate(BaseModel):
    items: list[OrderItemCreate]
    shipping_address: Optional[dict[str, Any]] = None


class Order(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    order_number: str
    status: OrderStatus
    total_amount: Decimal
    shipping_address: Optional[dict[str, Any]]
    created_at: datetime
    updated_at: datetime
    shipped_at: Optional[datetime]
    delivered_at: Optional[datetime]


class OrderWithItems(Order):
    items: list[OrderItem] = []


# Stock reservation models
class StockReservation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    product_id: UUID
    order_id: UUID
    quantity: int
    expires_at: datetime
    is_confirmed: bool
    created_at: datetime


# Notification models
class NotificationCreate(BaseModel):
    user_id: UUID
    type: NotificationType
    template_name: str
    template_data: dict[str, Any] = {}
    recipient: str
    subject: Optional[str] = None


class Notification(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    type: NotificationType
    status: NotificationStatus
    template_name: str
    template_data: dict[str, Any]
    recipient: str
    subject: Optional[str]
    content: Optional[str]
    error_message: Optional[str]
    created_at: datetime
    sent_at: Optional[datetime]
    failed_at: Optional[datetime]


# Service health models
class ServiceHealth(BaseModel):
    service_name: str
    status: str
    version: str
    uptime_seconds: float
    database: str
    timestamp: datetime


# Common response models
class MessageResponse(BaseModel):
    message: str


class ErrorResponse(BaseModel):
    error: str
    details: Optional[dict[str, Any]] = None
