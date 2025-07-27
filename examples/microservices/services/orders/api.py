"""Order service API endpoints."""

from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from jose import JWTError, jwt

from services.users.api import JWT_ALGORITHM, JWT_SECRET, HTTPAuthorizationCredentials, security
from shared.events import EventTypes, event_bus
from shared.models import Order, OrderCreate, OrderStatus, OrderWithItems
from shared.resilience import ServiceClient

router = APIRouter(prefix="/orders", tags=["Orders"])

# Service clients
inventory_client = ServiceClient("inventory-service")


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> UUID:
    """Get current user ID from JWT token."""
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        return UUID(user_id)

    except (JWTError, ValueError) as e:
        raise HTTPException(status_code=401, detail="Invalid token") from e


@router.post("/", response_model=Order)
async def create_order(
    request: Request, order_data: OrderCreate, user_id: UUID = Depends(get_current_user_id)
):
    """Create a new order."""
    db = request.app.state.db

    # Validate products and calculate total
    total_amount = Decimal("0")
    item_prices = {}

    for item in order_data.items:
        # Get product info from inventory service
        try:
            response = await inventory_client.get(f"/api/products/{item.product_id}")
            product = response.json()

            if not product.get("is_active"):
                raise HTTPException(
                    status_code=400, detail=f"Product {item.product_id} is not available"
                )

            # Check stock availability
            available = product.get("stock_quantity", 0) - product.get("reserved_quantity", 0)
            if available < item.quantity:
                raise HTTPException(
                    status_code=400, detail=f"Insufficient stock for product {item.product_id}"
                )

            # Calculate prices
            unit_price = Decimal(str(product["price"]))
            total_price = unit_price * item.quantity

            item_prices[item.product_id] = {"unit_price": unit_price, "total_price": total_price}

            total_amount += total_price

        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Failed to validate product {item.product_id}: {str(e)}"
            ) from e

    # Create order
    order = await db.create_order(user_id, order_data, total_amount)

    # Update order items with pricing
    await db.update_order_items_pricing(order.id, item_prices)

    # Reserve inventory
    for item in order_data.items:
        await event_bus.publish(
            EventTypes.STOCK_RESERVED,
            {
                "order_id": str(order.id),
                "product_id": str(item.product_id),
                "quantity": item.quantity,
            },
        )

    # Publish order created event
    await event_bus.publish(
        EventTypes.ORDER_CREATED,
        {
            "order_id": str(order.id),
            "user_id": str(user_id),
            "total_amount": str(total_amount),
            "items": [
                {"product_id": str(item.product_id), "quantity": item.quantity}
                for item in order_data.items
            ],
        },
        aggregate_id=order.id,
        aggregate_type="order",
    )

    return order


@router.get("/", response_model=list[Order])
async def list_orders(
    request: Request,
    user_id: UUID = Depends(get_current_user_id),
    limit: int = 10,
    offset: int = 0,
    status: Optional[OrderStatus] = None,
):
    """List user's orders."""
    db = request.app.state.db

    orders = await db.list_user_orders(user_id=user_id, limit=limit, offset=offset, status=status)

    return orders


@router.get("/{order_id}", response_model=OrderWithItems)
async def get_order(request: Request, order_id: UUID, user_id: UUID = Depends(get_current_user_id)):
    """Get order details."""
    db = request.app.state.db

    order = await db.get_order_by_user(order_id, user_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return order


@router.post("/{order_id}/cancel", response_model=Order)
async def cancel_order(
    request: Request, order_id: UUID, user_id: UUID = Depends(get_current_user_id)
):
    """Cancel an order."""
    db = request.app.state.db

    # Get order
    order = await db.get_order_by_user(order_id, user_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Check if order can be cancelled
    if order.status not in [OrderStatus.PENDING, OrderStatus.CONFIRMED]:
        raise HTTPException(status_code=400, detail=f"Cannot cancel order in {order.status} status")

    # Cancel order
    cancelled_order = await db.cancel_order(order_id)
    if not cancelled_order:
        raise HTTPException(status_code=500, detail="Failed to cancel order")

    # Release inventory reservations
    for item in order.items:
        await event_bus.publish(
            EventTypes.STOCK_RELEASED,
            {
                "order_id": str(order_id),
                "product_id": str(item.product_id),
                "quantity": item.quantity,
            },
        )

    # Publish order cancelled event
    await event_bus.publish(
        EventTypes.ORDER_CANCELLED,
        {
            "order_id": str(order_id),
            "user_id": str(user_id),
            "reason": "User requested cancellation",
        },
        aggregate_id=order_id,
        aggregate_type="order",
    )

    return cancelled_order


@router.get("/{order_id}/status", response_model=dict)
async def get_order_status(
    request: Request, order_id: UUID, user_id: UUID = Depends(get_current_user_id)
):
    """Get order status details."""
    db = request.app.state.db

    order = await db.get_order_by_user(order_id, user_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return {
        "order_id": order.id,
        "status": order.status,
        "created_at": order.created_at,
        "updated_at": order.updated_at,
        "shipped_at": order.shipped_at,
        "delivered_at": order.delivered_at,
    }


@router.get("/stats/summary", response_model=dict)
async def get_order_stats(request: Request, user_id: UUID = Depends(get_current_user_id)):
    """Get user's order statistics."""
    db = request.app.state.db

    stats = await db.get_order_stats(user_id)
    return stats
