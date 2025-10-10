"""Database operations for order service."""

from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from shared.database import ServiceDatabase
from shared.models import Order, OrderCreate, OrderItem, OrderStatus, OrderWithItems


class OrderDatabase(ServiceDatabase):
    """Order service database operations."""

    def __init__(self):
        super().__init__("order-service", "orders")

    async def create_order(
        self, user_id: UUID, order_data: OrderCreate, total_amount: Decimal
    ) -> Order:
        """Create a new order."""
        order_number = f"ORD-{datetime.utcnow().strftime('%Y%m%d')}-{uuid4().hex[:8].upper()}"

        async with await self.transaction() as tx:
            # Create order
            order_result = await tx.fetch_one(
                """
                INSERT INTO {{tables.orders}} (
                    user_id, order_number, status, total_amount, shipping_address
                )
                VALUES ($1, $2, $3, $4, $5)
                RETURNING *
            """,
                user_id,
                order_number,
                OrderStatus.PENDING.value,
                total_amount,
                order_data.shipping_address or {},
            )

            if not order_result:
                raise ValueError("Failed to create order")

            order = Order(**order_result)

            # Create order items
            for item in order_data.items:
                await tx.execute(
                    """
                    INSERT INTO {{tables.order_items}} (
                        order_id, product_id, quantity, unit_price, total_price
                    )
                    VALUES ($1, $2, $3, $4, $5)
                """,
                    order.id,
                    item.product_id,
                    item.quantity,
                    0,  # Will be updated with actual price
                    0,  # Will be updated with actual price
                )

            return order

    async def get_order(self, order_id: UUID) -> Optional[OrderWithItems]:
        """Get order with items."""
        # Get order
        order_result = await self.fetch_one(
            "SELECT * FROM {{tables.orders}} WHERE id = $1", order_id
        )

        if not order_result:
            return None

        # Get order items
        items_results = await self.fetch_all(
            "SELECT * FROM {{tables.order_items}} WHERE order_id = $1", order_id
        )

        items = [OrderItem(**item) for item in items_results]

        return OrderWithItems(**order_result, items=items)

    async def get_order_by_user(self, order_id: UUID, user_id: UUID) -> Optional[OrderWithItems]:
        """Get order ensuring it belongs to the user."""
        order = await self.get_order(order_id)
        if order and order.user_id == user_id:
            return order
        return None

    async def list_user_orders(
        self, user_id: UUID, limit: int = 10, offset: int = 0, status: Optional[OrderStatus] = None
    ) -> list[Order]:
        """List orders for a user."""
        query = "SELECT * FROM {{tables.orders}} WHERE user_id = $1"
        params = [user_id]
        param_count = 1

        if status:
            param_count += 1
            query += f" AND status = ${param_count}"
            params.append(status.value)

        query += " ORDER BY created_at DESC"

        param_count += 1
        query += f" LIMIT ${param_count}"
        params.append(limit)

        param_count += 1
        query += f" OFFSET ${param_count}"
        params.append(offset)

        results = await self.fetch_all(query, *params)
        return [Order(**row) for row in results]

    async def update_order_status(self, order_id: UUID, status: OrderStatus) -> Optional[Order]:
        """Update order status."""
        # Set additional timestamps based on status
        extra_updates = ""
        if status == OrderStatus.SHIPPED:
            extra_updates = ", shipped_at = NOW()"
        elif status == OrderStatus.DELIVERED:
            extra_updates = ", delivered_at = NOW()"

        result = await self.fetch_one(
            f"""
            UPDATE {{tables.orders}}
            SET status = $2, updated_at = NOW(){extra_updates}
            WHERE id = $1
            RETURNING *
        """,
            order_id,
            status.value,
        )

        return Order(**result) if result else None

    async def cancel_order(self, order_id: UUID) -> Optional[Order]:
        """Cancel an order."""
        return await self.update_order_status(order_id, OrderStatus.CANCELLED)

    async def update_order_items_pricing(
        self, order_id: UUID, item_prices: dict[UUID, dict[str, Decimal]]
    ) -> None:
        """Update order items with actual pricing."""
        async with await self.transaction() as tx:
            total_amount = Decimal("0")

            for product_id, prices in item_prices.items():
                await tx.execute(
                    """
                    UPDATE {{tables.order_items}}
                    SET unit_price = $3, total_price = $4
                    WHERE order_id = $1 AND product_id = $2
                """,
                    order_id,
                    product_id,
                    prices["unit_price"],
                    prices["total_price"],
                )

                total_amount += prices["total_price"]

            # Update order total
            await tx.execute(
                """
                UPDATE {{tables.orders}}
                SET total_amount = $2
                WHERE id = $1
            """,
                order_id,
                total_amount,
            )

    async def get_pending_orders(self, limit: int = 100) -> list[Order]:
        """Get pending orders for processing."""
        results = await self.fetch_all(
            """
            SELECT * FROM {{tables.orders}}
            WHERE status = $1
            ORDER BY created_at
            LIMIT $2
        """,
            OrderStatus.PENDING.value,
            limit,
        )

        return [Order(**row) for row in results]

    async def get_order_stats(self, user_id: Optional[UUID] = None) -> dict[str, Any]:
        """Get order statistics."""
        if user_id:
            stats = await self.fetch_one(
                """
                SELECT
                    COUNT(*) as total_orders,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending_orders,
                    COUNT(*) FILTER (WHERE status = 'delivered') as delivered_orders,
                    COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled_orders,
                    SUM(total_amount) FILTER (WHERE status != 'cancelled') as total_revenue
                FROM {{tables.orders}}
                WHERE user_id = $1
            """,
                user_id,
            )
        else:
            stats = await self.fetch_one(
                """
                SELECT
                    COUNT(*) as total_orders,
                    COUNT(*) FILTER (WHERE status = 'pending') as pending_orders,
                    COUNT(*) FILTER (WHERE status = 'delivered') as delivered_orders,
                    COUNT(*) FILTER (WHERE status = 'cancelled') as cancelled_orders,
                    SUM(total_amount) FILTER (WHERE status != 'cancelled') as total_revenue
                FROM {{tables.orders}}
            """
            )

        return dict(stats) if stats else {}
