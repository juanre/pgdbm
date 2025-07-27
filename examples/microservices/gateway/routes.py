"""Gateway routes that proxy to microservices."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from shared.models import OrderCreate, ProductCreate, UserCreate
from shared.resilience import ServiceClient

router = APIRouter(prefix="/api", tags=["Gateway"])
security = HTTPBearer()


# Service clients
user_client = ServiceClient("user-service")
order_client = ServiceClient("order-service")
inventory_client = ServiceClient("inventory-service")
notification_client = ServiceClient("notification-service")


async def get_auth_header(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[str]:
    """Extract authorization header."""
    if credentials:
        return f"Bearer {credentials.credentials}"
    return None


# User service routes
@router.post("/users/register")
async def register_user(user: UserCreate):
    """Register a new user."""
    try:
        response = await user_client.post("/api/users/register", json=user.model_dump())
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/users/login")
async def login_user(credentials: dict[str, str]):
    """Login user."""
    try:
        response = await user_client.post("/api/users/login", json=credentials)
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/users/me")
async def get_current_user(auth: Optional[str] = Depends(get_auth_header)):
    """Get current user."""
    if not auth:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        response = await user_client.get("/api/users/me", headers={"Authorization": auth})
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# Order service routes
@router.post("/orders")
async def create_order(order: OrderCreate, auth: Optional[str] = Depends(get_auth_header)):
    """Create a new order."""
    if not auth:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        response = await order_client.post(
            "/api/orders", json=order.model_dump(), headers={"Authorization": auth}
        )
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/orders")
async def list_orders(
    auth: Optional[str] = Depends(get_auth_header), limit: int = 10, offset: int = 0
):
    """List user's orders."""
    if not auth:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        response = await order_client.get(
            "/api/orders",
            params={"limit": limit, "offset": offset},
            headers={"Authorization": auth},
        )
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/orders/{order_id}")
async def get_order(order_id: UUID, auth: Optional[str] = Depends(get_auth_header)):
    """Get order details."""
    if not auth:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        response = await order_client.get(
            f"/api/orders/{order_id}", headers={"Authorization": auth}
        )
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/orders/{order_id}/cancel")
async def cancel_order(order_id: UUID, auth: Optional[str] = Depends(get_auth_header)):
    """Cancel an order."""
    if not auth:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        response = await order_client.post(
            f"/api/orders/{order_id}/cancel", headers={"Authorization": auth}
        )
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# Inventory service routes
@router.get("/inventory/products")
async def list_products(limit: int = 10, offset: int = 0, category: Optional[str] = None):
    """List available products."""
    try:
        params = {"limit": limit, "offset": offset}
        if category:
            params["category"] = category

        response = await inventory_client.get("/api/products", params=params)
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/inventory/products/{product_id}")
async def get_product(product_id: UUID):
    """Get product details."""
    try:
        response = await inventory_client.get(f"/api/products/{product_id}")
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/inventory/products")
async def create_product(product: ProductCreate, auth: Optional[str] = Depends(get_auth_header)):
    """Create a new product (admin only)."""
    if not auth:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        response = await inventory_client.post(
            "/api/products", json=product.model_dump(), headers={"Authorization": auth}
        )
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.put("/inventory/products/{product_id}/stock")
async def update_stock(
    product_id: UUID, stock_update: dict[str, int], auth: Optional[str] = Depends(get_auth_header)
):
    """Update product stock (admin only)."""
    if not auth:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        response = await inventory_client.put(
            f"/api/products/{product_id}/stock", json=stock_update, headers={"Authorization": auth}
        )
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# Notification service routes
@router.get("/notifications")
async def list_notifications(
    auth: Optional[str] = Depends(get_auth_header),
    status: Optional[str] = None,
    limit: int = 10,
    offset: int = 0,
):
    """List user's notifications."""
    if not auth:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        params = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status

        response = await notification_client.get(
            "/api/notifications", params=params, headers={"Authorization": auth}
        )
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/notifications/{notification_id}/mark-read")
async def mark_notification_read(
    notification_id: UUID, auth: Optional[str] = Depends(get_auth_header)
):
    """Mark notification as read."""
    if not auth:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        response = await notification_client.post(
            f"/api/notifications/{notification_id}/mark-read", headers={"Authorization": auth}
        )
        return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# Service discovery endpoint
@router.get("/services")
async def list_services():
    """List all registered services."""
    from shared.database import SharedDatabaseManager

    try:
        shared_db = await SharedDatabaseManager.get_instance()
        db = shared_db.get_manager()

        services = await db.fetch_all(
            """
            SELECT service_name, service_url, is_healthy, last_heartbeat
            FROM service_registry
            ORDER BY service_name
        """
        )

        return services
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
