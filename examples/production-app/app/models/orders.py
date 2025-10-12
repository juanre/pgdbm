"""Order models."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class OrderStatus(str, Enum):
    """Order status enum."""

    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


class OrderItemBase(BaseModel):
    """Base order item model."""

    product_id: int
    quantity: int = Field(..., gt=0)
    price: Decimal = Field(..., decimal_places=2)


class OrderItemCreate(OrderItemBase):
    """Model for creating order item."""

    pass


class OrderItemResponse(OrderItemBase):
    """Order item response model."""

    id: int
    order_id: int
    total: Decimal

    class Config:
        from_attributes = True


class OrderBase(BaseModel):
    """Base order model."""

    user_id: int
    status: OrderStatus = OrderStatus.PENDING
    shipping_address: str
    notes: Optional[str] = None


class OrderCreate(OrderBase):
    """Model for creating an order."""

    items: list[OrderItemCreate]


class OrderUpdate(BaseModel):
    """Model for updating an order."""

    status: Optional[OrderStatus] = None
    shipping_address: Optional[str] = None
    notes: Optional[str] = None


class OrderResponse(OrderBase):
    """Order response model."""

    id: int
    order_number: str
    total_amount: Decimal
    created_at: datetime
    updated_at: datetime
    items: list[OrderItemResponse] = []

    class Config:
        from_attributes = True
