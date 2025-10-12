"""Order management endpoints."""

import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.dependencies import OrdersDB
from app.models.orders import OrderCreate, OrderResponse, OrderStatus

router = APIRouter(prefix="/orders")


@router.post("", response_model=OrderResponse)
async def create_order(order: OrderCreate, db: OrdersDB):
    """Create a new order with items."""
    async with db.transaction() as conn:
        # Generate order number
        order_number = f"ORD-{uuid.uuid4().hex[:8].upper()}"

        # Calculate total
        total_amount = sum(item.price * item.quantity for item in order.items)

        # Create order
        order_result = await conn.fetch_one(
            """
            INSERT INTO {{tables.orders}}
            (order_number, user_id, status, total_amount, shipping_address, notes)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING id, order_number, user_id, status, total_amount,
                      shipping_address, notes, created_at, updated_at
            """,
            order_number,
            order.user_id,
            order.status.value,
            total_amount,
            order.shipping_address,
            order.notes,
        )

        order_dict = dict(order_result)
        order_id = order_dict["id"]

        # Create order items
        items = []
        for item in order.items:
            item_total = item.price * item.quantity
            item_result = await conn.fetch_one(
                """
                INSERT INTO {{tables.order_items}}
                (order_id, product_id, quantity, price, total)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id, order_id, product_id, quantity, price, total
                """,
                order_id,
                item.product_id,
                item.quantity,
                item.price,
                item_total,
            )
            items.append(dict(item_result))

        order_dict["items"] = items

    return OrderResponse(**order_dict)


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(order_id: int, db: OrdersDB):
    """Get an order with its items."""
    # Get order
    order = await db.fetch_one(
        """
        SELECT id, order_number, user_id, status, total_amount,
               shipping_address, notes, created_at, updated_at
        FROM {{tables.orders}}
        WHERE id = $1
        """,
        order_id,
    )

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order_dict = dict(order)

    # Get order items
    items = await db.fetch_all(
        """
        SELECT id, order_id, product_id, quantity, price, total
        FROM {{tables.order_items}}
        WHERE order_id = $1
        """,
        order_id,
    )

    order_dict["items"] = [dict(item) for item in items]

    return OrderResponse(**order_dict)


@router.put("/{order_id}/status", response_model=OrderResponse)
async def update_order_status(order_id: int, status: OrderStatus, db: OrdersDB):
    """Update order status."""
    order = await db.fetch_one(
        """
        UPDATE {{tables.orders}}
        SET status = $1, updated_at = NOW()
        WHERE id = $2
        RETURNING id, order_number, user_id, status, total_amount,
                  shipping_address, notes, created_at, updated_at
        """,
        status.value,
        order_id,
    )

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order_dict = dict(order)

    # Get order items
    items = await db.fetch_all(
        """
        SELECT id, order_id, product_id, quantity, price, total
        FROM {{tables.order_items}}
        WHERE order_id = $1
        """,
        order_id,
    )

    order_dict["items"] = [dict(item) for item in items]

    return OrderResponse(**order_dict)


@router.get("", response_model=list[OrderResponse])
async def list_orders(
    db: OrdersDB,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    status: Optional[OrderStatus] = None,
    user_id: Optional[int] = None,
):
    """List orders with filtering and pagination."""
    query = """
        SELECT id, order_number, user_id, status, total_amount,
               shipping_address, notes, created_at, updated_at
        FROM {{tables.orders}}
    """

    conditions = []
    params = []
    param_count = 1

    if status is not None:
        conditions.append(f"status = ${param_count}")
        params.append(status.value)
        param_count += 1

    if user_id is not None:
        conditions.append(f"user_id = ${param_count}")
        params.append(user_id)
        param_count += 1

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += f" ORDER BY created_at DESC LIMIT {limit} OFFSET {skip}"

    orders = await db.fetch_all(query, *params)

    # For simplicity, not fetching items for list view
    # In production, you might want to include item count or use a join
    return [OrderResponse(**dict(order), items=[]) for order in orders]
