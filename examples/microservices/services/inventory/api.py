"""Inventory service API endpoints."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request

from shared.events import EventTypes, event_bus
from shared.models import MessageResponse, Product, ProductCreate, ProductUpdate

router = APIRouter(prefix="/products", tags=["Products"])


@router.post("/", response_model=Product)
async def create_product(request: Request, product: ProductCreate):
    """Create a new product."""
    db = request.app.state.db

    # Check if SKU already exists
    existing = await db.get_product_by_sku(product.sku)
    if existing:
        raise HTTPException(status_code=400, detail="SKU already exists")

    # Create product
    new_product = await db.create_product(product)

    # Publish event
    await event_bus.publish(
        EventTypes.STOCK_UPDATED,
        {
            "product_id": str(new_product.id),
            "sku": new_product.sku,
            "stock_quantity": new_product.stock_quantity,
            "action": "created",
        },
        aggregate_id=new_product.id,
        aggregate_type="product",
    )

    return new_product


@router.get("/", response_model=list[Product])
async def list_products(
    request: Request, limit: int = 10, offset: int = 0, is_active: Optional[bool] = True
):
    """List available products."""
    db = request.app.state.db

    products = await db.list_products(limit=limit, offset=offset, is_active=is_active)

    return products


@router.get("/{product_id}", response_model=Product)
async def get_product(request: Request, product_id: UUID):
    """Get product details."""
    db = request.app.state.db

    product = await db.get_product(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return product


@router.patch("/{product_id}", response_model=Product)
async def update_product(request: Request, product_id: UUID, update: ProductUpdate):
    """Update product information."""
    db = request.app.state.db

    product = await db.update_product(product_id, update)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Publish event if relevant fields changed
    if update.stock_quantity is not None or update.is_active is not None:
        await event_bus.publish(
            EventTypes.STOCK_UPDATED,
            {
                "product_id": str(product_id),
                "sku": product.sku,
                "stock_quantity": product.stock_quantity,
                "is_active": product.is_active,
                "action": "updated",
            },
            aggregate_id=product_id,
            aggregate_type="product",
        )

    return product


@router.put("/{product_id}/stock", response_model=Product)
async def update_stock(request: Request, product_id: UUID, stock_update: dict):
    """Update product stock quantity."""
    db = request.app.state.db

    quantity_change = stock_update.get("quantity_change", 0)
    if not isinstance(quantity_change, int):
        raise HTTPException(status_code=400, detail="quantity_change must be an integer")

    product = await db.update_stock(product_id, quantity_change)
    if not product:
        raise HTTPException(
            status_code=400,
            detail="Failed to update stock (product not found or insufficient stock)",
        )

    # Publish event
    await event_bus.publish(
        EventTypes.STOCK_UPDATED,
        {
            "product_id": str(product_id),
            "sku": product.sku,
            "quantity_change": quantity_change,
            "new_quantity": product.stock_quantity,
            "action": "stock_adjusted",
        },
        aggregate_id=product_id,
        aggregate_type="product",
    )

    # Check for low stock
    if product.stock_quantity < 10 and product.is_active:
        await event_bus.publish(
            EventTypes.LOW_STOCK_ALERT,
            {
                "product_id": str(product_id),
                "sku": product.sku,
                "stock_quantity": product.stock_quantity,
                "threshold": 10,
            },
        )

    return product


@router.post("/{product_id}/reserve")
async def reserve_stock(request: Request, product_id: UUID, reservation: dict):
    """Reserve stock for an order (internal endpoint)."""
    db = request.app.state.db

    order_id = UUID(reservation.get("order_id"))
    quantity = reservation.get("quantity", 0)

    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be positive")

    stock_reservation = await db.reserve_stock(product_id, order_id, quantity)
    if not stock_reservation:
        raise HTTPException(
            status_code=400,
            detail="Failed to reserve stock (product not found or insufficient stock)",
        )

    return {
        "reservation_id": stock_reservation.id,
        "product_id": product_id,
        "order_id": order_id,
        "quantity": quantity,
        "expires_at": stock_reservation.expires_at,
    }


@router.delete("/reservations/{order_id}/{product_id}")
async def release_reservation(request: Request, order_id: UUID, product_id: UUID):
    """Release stock reservation."""
    db = request.app.state.db

    success = await db.release_reservation(order_id, product_id)
    if not success:
        raise HTTPException(status_code=404, detail="Reservation not found")

    return MessageResponse(message="Stock reservation released")


@router.post("/cleanup-expired")
async def cleanup_expired_reservations(request: Request):
    """Clean up expired stock reservations."""
    db = request.app.state.db

    count = await db.cleanup_expired_reservations()

    return {"message": f"Cleaned up {count} expired reservations"}
