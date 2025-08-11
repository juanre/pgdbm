"""Event system for inter-service communication."""

import asyncio
import json
from datetime import datetime
from typing import Any, Callable, Optional
from uuid import UUID, uuid4

from .database import SharedDatabaseManager


class Event:
    """Represents a domain event."""

    def __init__(
        self,
        event_type: str,
        data: dict[str, Any],
        aggregate_id: Optional[UUID] = None,
        aggregate_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ):
        self.id = uuid4()
        self.event_type = event_type
        self.data = data
        self.aggregate_id = aggregate_id
        self.aggregate_type = aggregate_type
        self.metadata = metadata or {}
        self.created_at = datetime.utcnow()


class EventBus:
    """Simple event bus for publishing and subscribing to events."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}
        self._db = None
        self._running = False
        self._task = None

    async def initialize(self) -> None:
        """Initialize the event bus."""
        shared = await SharedDatabaseManager.get_instance()
        self._db = shared.get_manager()
        self._running = True

        # Start background agent to process events
        self._task = asyncio.create_task(self._process_events())

    async def close(self) -> None:
        """Close the event bus."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def subscribe(self, event_type: str, handler: Callable) -> None:
        """Subscribe to an event type."""
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        print(f"Handler subscribed to '{event_type}' events")

    async def publish(
        self,
        event_type: str,
        data: dict[str, Any],
        aggregate_id: Optional[UUID] = None,
        aggregate_type: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> UUID:
        """Publish an event."""
        if not self._db:
            raise RuntimeError("EventBus not initialized")

        event = Event(event_type, data, aggregate_id, aggregate_type, metadata)

        # Store event in database
        await self._db.execute(
            """
            INSERT INTO events (
                id, event_type, aggregate_id, aggregate_type,
                event_data, metadata, created_at
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        """,
            event.id,
            event.event_type,
            event.aggregate_id,
            event.aggregate_type,
            json.dumps(event.data),
            json.dumps(event.metadata),
            event.created_at,
        )

        print(f"Published event: {event_type} (ID: {event.id})")
        return event.id

    async def _process_events(self) -> None:
        """Background agent to process unprocessed events."""
        while self._running:
            try:
                # Fetch unprocessed events
                events = await self._db.fetch_all(
                    """
                    SELECT * FROM events
                    WHERE processed_at IS NULL
                    ORDER BY created_at
                    LIMIT 100
                    FOR UPDATE SKIP LOCKED
                """
                )

                for event_row in events:
                    await self._handle_event(event_row)

                # Sleep if no events
                if not events:
                    await asyncio.sleep(0.1)

            except Exception as e:
                print(f"Error processing events: {e}")
                await asyncio.sleep(1)

    async def _handle_event(self, event_row: dict[str, Any]) -> None:
        """Handle a single event."""
        event_type = event_row["event_type"]
        event_data = event_row["event_data"]

        # Get handlers for this event type
        handlers = self._handlers.get(event_type, [])

        # Execute all handlers
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event_data)
                else:
                    handler(event_data)
            except Exception as e:
                print(f"Error in event handler for {event_type}: {e}")

        # Mark event as processed
        await self._db.execute(
            """
            UPDATE events
            SET processed_at = NOW()
            WHERE id = $1
        """,
            event_row["id"],
        )


# Global event bus instance
event_bus = EventBus()


def event_handler(event_type: str):
    """Decorator for event handlers."""

    def decorator(func: Callable):
        event_bus.subscribe(event_type, func)
        return func

    return decorator


# Common event types
class EventTypes:
    # User events
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"

    # Order events
    ORDER_CREATED = "order.created"
    ORDER_CONFIRMED = "order.confirmed"
    ORDER_SHIPPED = "order.shipped"
    ORDER_DELIVERED = "order.delivered"
    ORDER_CANCELLED = "order.cancelled"

    # Inventory events
    STOCK_RESERVED = "inventory.stock_reserved"
    STOCK_RELEASED = "inventory.stock_released"
    STOCK_UPDATED = "inventory.stock_updated"
    LOW_STOCK_ALERT = "inventory.low_stock_alert"

    # Payment events
    PAYMENT_RECEIVED = "payment.received"
    PAYMENT_FAILED = "payment.failed"
    REFUND_ISSUED = "payment.refund_issued"
