"""Event handlers for inventory service."""

from uuid import UUID

from shared.events import EventTypes, event_handler


@event_handler(EventTypes.STOCK_RESERVED)
async def handle_stock_reservation(event_data: dict):
    """Handle stock reservation request from order service."""
    from .db import InventoryDatabase

    order_id = UUID(event_data["order_id"])
    product_id = UUID(event_data["product_id"])
    quantity = event_data["quantity"]

    print(f"Reserving {quantity} units of product {product_id} for order {order_id}")

    # Reserve stock
    db = InventoryDatabase()
    await db.initialize()

    reservation = await db.reserve_stock(product_id, order_id, quantity)
    if reservation:
        print(f"Stock reserved successfully: {reservation.id}")
    else:
        print(f"Failed to reserve stock for order {order_id}")
        # In a real system, we'd publish a failure event


@event_handler(EventTypes.STOCK_RELEASED)
async def handle_stock_release(event_data: dict):
    """Handle stock release request (e.g., order cancelled)."""
    from .db import InventoryDatabase

    order_id = UUID(event_data["order_id"])
    product_id = UUID(event_data["product_id"])

    print(f"Releasing stock for product {product_id} from order {order_id}")

    # Release reservation
    db = InventoryDatabase()
    await db.initialize()

    success = await db.release_reservation(order_id, product_id)
    if success:
        print(f"Stock released successfully for order {order_id}")
    else:
        print(f"No reservation found to release for order {order_id}")
