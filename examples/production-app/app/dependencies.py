"""FastAPI dependency injection for clean architecture."""

from typing import Annotated

from fastapi import Depends, HTTPException
from pgdbm import AsyncDatabaseManager

from app.database import db_infrastructure


async def get_users_db() -> AsyncDatabaseManager:
    """Get database manager for users service."""
    try:
        return db_infrastructure.get_manager('users')
    except ValueError as e:
        raise HTTPException(status_code=500, detail="Users database not initialized")


async def get_orders_db() -> AsyncDatabaseManager:
    """Get database manager for orders service."""
    try:
        return db_infrastructure.get_manager('orders')
    except ValueError as e:
        raise HTTPException(status_code=500, detail="Orders database not initialized")


async def get_analytics_db() -> AsyncDatabaseManager:
    """Get database manager for analytics service."""
    try:
        return db_infrastructure.get_manager('analytics')
    except ValueError as e:
        raise HTTPException(status_code=500, detail="Analytics database not initialized")


# Type aliases for cleaner function signatures
UsersDB = Annotated[AsyncDatabaseManager, Depends(get_users_db)]
OrdersDB = Annotated[AsyncDatabaseManager, Depends(get_orders_db)]
AnalyticsDB = Annotated[AsyncDatabaseManager, Depends(get_analytics_db)]