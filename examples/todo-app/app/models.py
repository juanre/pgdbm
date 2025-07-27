"""Pydantic models for the todo application."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class TodoBase(BaseModel):
    """Base todo model."""

    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class TodoCreate(TodoBase):
    """Model for creating a todo."""

    pass


class TodoUpdate(BaseModel):
    """Model for updating a todo."""

    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    completed: Optional[bool] = None


class Todo(TodoBase):
    """Complete todo model."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    completed: bool
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class TodoList(BaseModel):
    """Paginated list of todos."""

    items: list[Todo]
    total: int
    limit: int
    offset: int
    has_more: bool


class HealthStatus(BaseModel):
    """Health check response."""

    status: str
    database: str
    pool: Optional[dict] = None
    todos: Optional[dict] = None
    error: Optional[str] = None


class ErrorResponse(BaseModel):
    """Error response model."""

    error: str
    detail: Optional[str] = None
    request_id: Optional[str] = None
