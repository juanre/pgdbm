"""Analytics models."""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel


class UserStats(BaseModel):
    """User statistics model."""

    total_users: int
    active_users: int
    new_users_today: int
    new_users_this_week: int
    new_users_this_month: int

    class Config:
        from_attributes = True


class OrderStats(BaseModel):
    """Order statistics model."""

    total_orders: int
    pending_orders: int
    processing_orders: int
    completed_orders: int
    cancelled_orders: int
    orders_today: int
    orders_this_week: int
    orders_this_month: int

    class Config:
        from_attributes = True


class RevenueStats(BaseModel):
    """Revenue statistics model."""

    total_revenue: Decimal
    revenue_today: Decimal
    revenue_this_week: Decimal
    revenue_this_month: Decimal
    average_order_value: Decimal

    class Config:
        from_attributes = True


class DailyRevenue(BaseModel):
    """Daily revenue model."""

    date: date
    revenue: Decimal
    order_count: int

    class Config:
        from_attributes = True


class Analytics(BaseModel):
    """Combined analytics model."""

    users: UserStats
    orders: OrderStats
    revenue: RevenueStats
    daily_revenue: list[DailyRevenue]
    generated_at: datetime

    class Config:
        from_attributes = True
