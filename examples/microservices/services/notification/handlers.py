"""Event handlers for notification service."""

from datetime import datetime
from uuid import UUID

from shared.database import SharedDatabaseManager
from shared.events import EventTypes, event_handler
from shared.models import NotificationStatus, NotificationType


async def send_notification(
    user_id: UUID,
    template_name: str,
    template_data: dict,
    notification_type: NotificationType = NotificationType.EMAIL,
):
    """Send a notification (simulated)."""
    shared = await SharedDatabaseManager.get_instance()
    db = shared.get_manager()

    # In a real system, this would:
    # 1. Look up user's contact info
    # 2. Render template with data
    # 3. Send via appropriate channel (email, SMS, etc.)
    # 4. Store notification record

    print(f"Sending {notification_type} notification '{template_name}' to user {user_id}")
    print(f"Template data: {template_data}")

    # Store notification record
    await db.execute(
        """
        INSERT INTO notifications (
            user_id, type, status, template_name, template_data,
            recipient, subject, content, sent_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
    """,
        user_id,
        notification_type.value,
        NotificationStatus.SENT.value,
        template_name,
        template_data,
        f"user-{user_id}@example.com",  # Simulated
        f"Notification: {template_name}",
        f"Rendered content for {template_name}",
        datetime.utcnow(),
    )


@event_handler(EventTypes.USER_CREATED)
async def handle_user_created(event_data: dict):
    """Send welcome email to new users."""
    user_id = UUID(event_data["user_id"])

    await send_notification(
        user_id=user_id,
        template_name="welcome_email",
        template_data={"name": event_data.get("name", "User"), "email": event_data.get("email")},
    )


@event_handler(EventTypes.ORDER_CREATED)
async def handle_order_created(event_data: dict):
    """Send order confirmation notification."""
    user_id = UUID(event_data["user_id"])
    order_id = event_data["order_id"]

    await send_notification(
        user_id=user_id,
        template_name="order_confirmation",
        template_data={
            "order_id": order_id,
            "total_amount": event_data.get("total_amount"),
            "items": event_data.get("items", []),
        },
    )


@event_handler(EventTypes.ORDER_CONFIRMED)
async def handle_order_confirmed(event_data: dict):
    """Send order payment confirmed notification."""
    user_id = UUID(event_data["user_id"])
    order_id = event_data["order_id"]

    await send_notification(
        user_id=user_id, template_name="payment_confirmed", template_data={"order_id": order_id}
    )


@event_handler(EventTypes.ORDER_SHIPPED)
async def handle_order_shipped(event_data: dict):
    """Send shipping notification."""
    user_id = UUID(event_data["user_id"])
    order_id = event_data["order_id"]

    await send_notification(
        user_id=user_id,
        template_name="order_shipped",
        template_data={
            "order_id": order_id,
            "tracking_number": event_data.get("tracking_number"),
            "carrier": event_data.get("carrier"),
        },
    )


@event_handler(EventTypes.LOW_STOCK_ALERT)
async def handle_low_stock_alert(event_data: dict):
    """Send low stock alert to admin."""
    # In a real system, this would notify inventory managers
    print(
        f"LOW STOCK ALERT: Product {event_data['sku']} has only {event_data['stock_quantity']} units left!"
    )

    # Could send to admin users
    shared = await SharedDatabaseManager.get_instance()
    db = shared.get_manager()

    # Get admin users (simplified - in real app would have proper admin role)
    admin_users = await db.fetch_all("SELECT id FROM users WHERE email LIKE '%admin%'")

    for admin in admin_users:
        await send_notification(
            user_id=admin["id"],
            template_name="low_stock_alert",
            template_data=event_data,
            notification_type=NotificationType.EMAIL,
        )
