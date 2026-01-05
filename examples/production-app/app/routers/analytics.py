"""Analytics endpoints for reporting."""

from datetime import datetime

from fastapi import APIRouter, Query

from app.dependencies import OrdersDB, UsersDB
from app.models.analytics import Analytics, OrderStats, RevenueStats, UserStats

router = APIRouter(prefix="/analytics")


@router.get("/users/stats", response_model=UserStats)
async def get_user_stats(db: UsersDB):
    """Get user statistics."""
    # Total users
    total = await db.fetch_value("SELECT COUNT(*) FROM {{tables.users}}")

    # Active users
    active = await db.fetch_value("SELECT COUNT(*) FROM {{tables.users}} WHERE is_active = true")

    # New users today
    today = await db.fetch_value(
        """
        SELECT COUNT(*) FROM {{tables.users}}
        WHERE created_at >= CURRENT_DATE
        """
    )

    # New users this week
    week = await db.fetch_value(
        """
        SELECT COUNT(*) FROM {{tables.users}}
        WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
        """
    )

    # New users this month
    month = await db.fetch_value(
        """
        SELECT COUNT(*) FROM {{tables.users}}
        WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
        """
    )

    return UserStats(
        total_users=total,
        active_users=active,
        new_users_today=today,
        new_users_this_week=week,
        new_users_this_month=month,
    )


@router.get("/orders/stats", response_model=OrderStats)
async def get_order_stats(db: OrdersDB):
    """Get order statistics."""
    # Status counts
    status_counts = await db.fetch_all(
        """
        SELECT status, COUNT(*) as count
        FROM {{tables.orders}}
        GROUP BY status
        """
    )

    status_map = {row["status"]: row["count"] for row in status_counts}

    # Total orders
    total = sum(status_map.values())

    # Orders today
    today = await db.fetch_value(
        """
        SELECT COUNT(*) FROM {{tables.orders}}
        WHERE created_at >= CURRENT_DATE
        """
    )

    # Orders this week
    week = await db.fetch_value(
        """
        SELECT COUNT(*) FROM {{tables.orders}}
        WHERE created_at >= CURRENT_DATE - INTERVAL '7 days'
        """
    )

    # Orders this month
    month = await db.fetch_value(
        """
        SELECT COUNT(*) FROM {{tables.orders}}
        WHERE created_at >= CURRENT_DATE - INTERVAL '30 days'
        """
    )

    return OrderStats(
        total_orders=total,
        pending_orders=status_map.get("pending", 0),
        processing_orders=status_map.get("processing", 0),
        completed_orders=status_map.get("delivered", 0),
        cancelled_orders=status_map.get("cancelled", 0),
        orders_today=today,
        orders_this_week=week,
        orders_this_month=month,
    )


@router.get("/revenue", response_model=RevenueStats)
async def get_revenue_stats(db: OrdersDB):
    """Get revenue statistics."""
    # Total revenue (excluding cancelled orders)
    total = await db.fetch_value(
        """
        SELECT COALESCE(SUM(total_amount), 0)
        FROM {{tables.orders}}
        WHERE status != 'cancelled'
        """
    )

    # Revenue today
    today = await db.fetch_value(
        """
        SELECT COALESCE(SUM(total_amount), 0)
        FROM {{tables.orders}}
        WHERE status != 'cancelled'
        AND created_at >= CURRENT_DATE
        """
    )

    # Revenue this week
    week = await db.fetch_value(
        """
        SELECT COALESCE(SUM(total_amount), 0)
        FROM {{tables.orders}}
        WHERE status != 'cancelled'
        AND created_at >= CURRENT_DATE - INTERVAL '7 days'
        """
    )

    # Revenue this month
    month = await db.fetch_value(
        """
        SELECT COALESCE(SUM(total_amount), 0)
        FROM {{tables.orders}}
        WHERE status != 'cancelled'
        AND created_at >= CURRENT_DATE - INTERVAL '30 days'
        """
    )

    # Average order value
    avg = await db.fetch_value(
        """
        SELECT COALESCE(AVG(total_amount), 0)
        FROM {{tables.orders}}
        WHERE status != 'cancelled'
        """
    )

    return RevenueStats(
        total_revenue=total,
        revenue_today=today,
        revenue_this_week=week,
        revenue_this_month=month,
        average_order_value=avg,
    )


@router.get("/dashboard", response_model=Analytics)
async def get_dashboard(
    users_db: UsersDB,
    orders_db: OrdersDB,
    days: int = Query(30, ge=1, le=365, description="Number of days for daily revenue"),
):
    """Get complete analytics dashboard."""
    # Get all stats
    user_stats = await get_user_stats(users_db)
    order_stats = await get_order_stats(orders_db)
    revenue_stats = await get_revenue_stats(orders_db)

    # Get daily revenue for chart
    daily_revenue = await orders_db.fetch_all(
        """
        SELECT
            DATE(created_at) as date,
            SUM(total_amount) as revenue,
            COUNT(*) as order_count
        FROM {{tables.orders}}
        WHERE status != 'cancelled'
        AND created_at >= CURRENT_DATE - INTERVAL '%s days'
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        """,
        days,
    )

    return Analytics(
        users=user_stats,
        orders=order_stats,
        revenue=revenue_stats,
        daily_revenue=[dict(row) for row in daily_revenue],
        generated_at=datetime.now(),
    )
