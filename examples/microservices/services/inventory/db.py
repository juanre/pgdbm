"""Database operations for inventory service."""

from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

from shared.database import ServiceDatabase
from shared.models import Product, ProductCreate, ProductUpdate, StockReservation


class InventoryDatabase(ServiceDatabase):
    """Inventory service database operations."""

    def __init__(self):
        super().__init__("inventory-service", "inventory")

    async def create_product(self, product: ProductCreate) -> Product:
        """Create a new product."""
        result = await self.fetch_one(
            """
            INSERT INTO {{tables.products}} (sku, name, description, price, stock_quantity)
            VALUES ($1, $2, $3, $4, $5)
            RETURNING *
        """,
            product.sku,
            product.name,
            product.description,
            product.price,
            product.stock_quantity,
        )

        if not result:
            raise ValueError("Failed to create product")

        return Product(**result)

    async def get_product(self, product_id: UUID) -> Optional[Product]:
        """Get product by ID."""
        result = await self.fetch_one("SELECT * FROM {{tables.products}} WHERE id = $1", product_id)

        return Product(**result) if result else None

    async def get_product_by_sku(self, sku: str) -> Optional[Product]:
        """Get product by SKU."""
        result = await self.fetch_one("SELECT * FROM {{tables.products}} WHERE sku = $1", sku)

        return Product(**result) if result else None

    async def list_products(
        self, limit: int = 10, offset: int = 0, is_active: Optional[bool] = True
    ) -> list[Product]:
        """List products with pagination."""
        query = "SELECT * FROM {{tables.products}} WHERE 1=1"
        params = []
        param_count = 0

        if is_active is not None:
            param_count += 1
            query += f" AND is_active = ${param_count}"
            params.append(is_active)

        query += " ORDER BY created_at DESC"

        param_count += 1
        query += f" LIMIT ${param_count}"
        params.append(limit)

        param_count += 1
        query += f" OFFSET ${param_count}"
        params.append(offset)

        results = await self.fetch_all(query, *params)
        return [Product(**row) for row in results]

    async def update_product(self, product_id: UUID, update: ProductUpdate) -> Optional[Product]:
        """Update product information."""
        fields = []
        params = []
        param_count = 0

        update_dict = update.model_dump(exclude_unset=True)

        for field, value in update_dict.items():
            if value is not None:
                param_count += 1
                fields.append(f"{field} = ${param_count}")
                params.append(value)

        if not fields:
            return await self.get_product(product_id)

        param_count += 1
        params.append(product_id)

        query = f"""
            UPDATE {{tables.products}}
            SET {', '.join(fields)}, updated_at = NOW()
            WHERE id = ${param_count}
            RETURNING *
        """

        result = await self.fetch_one(query, *params)
        return Product(**result) if result else None

    async def update_stock(self, product_id: UUID, quantity_change: int) -> Optional[Product]:
        """Update product stock quantity."""
        result = await self.fetch_one(
            """
            UPDATE {{tables.products}}
            SET stock_quantity = stock_quantity + $2, updated_at = NOW()
            WHERE id = $1 AND stock_quantity + $2 >= 0
            RETURNING *
        """,
            product_id,
            quantity_change,
        )

        return Product(**result) if result else None

    async def reserve_stock(
        self, product_id: UUID, order_id: UUID, quantity: int, expiration_minutes: int = 30
    ) -> Optional[StockReservation]:
        """Reserve stock for an order."""
        expires_at = datetime.utcnow() + timedelta(minutes=expiration_minutes)

        async with await self.transaction() as tx:
            # Check available stock
            product_row = await tx.fetch_one(
                "SELECT * FROM {{tables.products}} WHERE id = $1", product_id
            )
            if not product_row:
                return None

            product = Product(**product_row)
            available = product.stock_quantity - product.reserved_quantity
            if available < quantity:
                return None

            # Create reservation
            reservation_result = await tx.fetch_one(
                """
                INSERT INTO {{tables.stock_reservations}} (
                    product_id, order_id, quantity, expires_at
                )
                VALUES ($1, $2, $3, $4)
                RETURNING *
            """,
                product_id,
                order_id,
                quantity,
                expires_at,
            )

            # Update reserved quantity
            await tx.execute(
                """
                UPDATE {{tables.products}}
                SET reserved_quantity = reserved_quantity + $2
                WHERE id = $1
            """,
                product_id,
                quantity,
            )

            return StockReservation(**reservation_result) if reservation_result else None

    async def confirm_reservation(self, reservation_id: UUID) -> bool:
        """Confirm a stock reservation."""
        async with await self.transaction() as tx:
            # Get reservation
            reservation = await tx.fetch_one(
                "SELECT * FROM {{tables.stock_reservations}} WHERE id = $1 AND NOT is_confirmed",
                reservation_id,
            )

            if not reservation:
                return False

            # Mark as confirmed
            await tx.execute(
                """
                UPDATE {{tables.stock_reservations}}
                SET is_confirmed = TRUE
                WHERE id = $1
            """,
                reservation_id,
            )

            # Reduce actual stock
            await tx.execute(
                """
                UPDATE {{tables.products}}
                SET stock_quantity = stock_quantity - $2,
                    reserved_quantity = reserved_quantity - $2
                WHERE id = $1
            """,
                reservation["product_id"],
                reservation["quantity"],
            )

            return True

    async def release_reservation(self, order_id: UUID, product_id: UUID) -> bool:
        """Release stock reservation."""
        async with await self.transaction() as tx:
            # Get reservation
            reservation = await tx.fetch_one(
                """
                SELECT * FROM {{tables.stock_reservations}}
                WHERE order_id = $1 AND product_id = $2 AND NOT is_confirmed
            """,
                order_id,
                product_id,
            )

            if not reservation:
                return False

            # Delete reservation
            await tx.execute(
                """
                DELETE FROM {{tables.stock_reservations}}
                WHERE order_id = $1 AND product_id = $2 AND NOT is_confirmed
            """,
                order_id,
                product_id,
            )

            # Update reserved quantity
            await tx.execute(
                """
                UPDATE {{tables.products}}
                SET reserved_quantity = reserved_quantity - $2
                WHERE id = $1
            """,
                product_id,
                reservation["quantity"],
            )

            return True

    async def cleanup_expired_reservations(self) -> int:
        """Clean up expired reservations."""
        result = await self.fetch_one(
            """
            WITH expired AS (
                DELETE FROM {{tables.stock_reservations}}
                WHERE expires_at < NOW() AND NOT is_confirmed
                RETURNING product_id, quantity
            )
            UPDATE {{tables.products}} p
            SET reserved_quantity = p.reserved_quantity - COALESCE(e.total_quantity, 0)
            FROM (
                SELECT product_id, SUM(quantity) as total_quantity
                FROM expired
                GROUP BY product_id
            ) e
            WHERE p.id = e.product_id
            RETURNING COUNT(*)
        """
        )

        return result["count"] if result else 0
