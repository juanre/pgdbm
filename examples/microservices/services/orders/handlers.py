"""Event handlers for order service."""

from uuid import UUID

from shared.events import EventTypes, event_handler
from shared.models import OrderStatus


@event_handler(EventTypes.STOCK_RESERVED)
async def handle_stock_reserved(event_data: dict):
    """Handle stock reserved event."""
    order_id = UUID(event_data["order_id"])
    print(f"Stock reserved for order {order_id}")

    # In a real system, we might check if all items are reserved
    # and then confirm the order


@event_handler(EventTypes.PAYMENT_RECEIVED)
async def handle_payment_received(event_data: dict):
    """Handle payment received event."""
    from .db import OrderDatabase

    order_id = UUID(event_data["order_id"])

    # Update order status to confirmed
    db = OrderDatabase()
    await db.initialize()

    order = await db.update_order_status(order_id, OrderStatus.CONFIRMED)
    if order:
        print(f"Order {order_id} confirmed after payment")

        # Publish order confirmed event
        from shared.events import event_bus

        await event_bus.publish(
            EventTypes.ORDER_CONFIRMED,
            {"order_id": str(order_id), "user_id": str(order.user_id)},
            aggregate_id=order_id,
            aggregate_type="order",
        )
