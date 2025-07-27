"""Todo API endpoints."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Path, Query, Request

from ..db import TodoDatabase, TodoNotFoundError
from ..models import Todo, TodoCreate, TodoList, TodoUpdate

router = APIRouter(prefix="/todos", tags=["todos"])


@router.get("", response_model=TodoList)
async def list_todos(
    request: Request,
    completed: Optional[bool] = Query(None, description="Filter by completion status"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of todos to return"),
    offset: int = Query(0, ge=0, description="Number of todos to skip"),
) -> TodoList:
    """List todos with optional filtering and pagination."""
    db: TodoDatabase = request.app.state.db

    todos = await db.list_todos(completed=completed, limit=limit, offset=offset)
    total = await db.count_todos(completed=completed)

    # Convert UUIDs to strings for each todo
    for todo in todos:
        todo["id"] = str(todo["id"])

    return TodoList(
        items=[Todo(**todo) for todo in todos],
        total=total,
        limit=limit,
        offset=offset,
        has_more=(offset + len(todos)) < total,
    )


@router.post("", response_model=Todo, status_code=201)
async def create_todo(request: Request, todo: TodoCreate) -> Todo:
    """Create a new todo."""
    db: TodoDatabase = request.app.state.db

    created_todo = await db.create_todo(title=todo.title, description=todo.description)

    created_todo["id"] = str(created_todo["id"])
    return Todo(**created_todo)


@router.get("/{todo_id}", response_model=Todo)
async def get_todo(request: Request, todo_id: str = Path(..., description="Todo ID")) -> Todo:
    """Get a specific todo by ID."""
    db: TodoDatabase = request.app.state.db

    try:
        todo = await db.get_todo(todo_id)
        todo["id"] = str(todo["id"])
        return Todo(**todo)
    except TodoNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Todo {todo_id} not found") from e


@router.put("/{todo_id}", response_model=Todo)
async def update_todo(request: Request, todo_id: str, update: TodoUpdate) -> Todo:
    """Update a todo."""
    db: TodoDatabase = request.app.state.db

    try:
        # Only pass non-None values
        update_data = {k: v for k, v in update.model_dump().items() if v is not None}

        updated_todo = await db.update_todo(todo_id, **update_data)
        updated_todo["id"] = str(updated_todo["id"])
        return Todo(**updated_todo)
    except TodoNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Todo {todo_id} not found") from e


@router.delete("/{todo_id}", status_code=204)
async def delete_todo(request: Request, todo_id: str = Path(..., description="Todo ID")) -> None:
    """Delete a todo."""
    db: TodoDatabase = request.app.state.db

    try:
        await db.delete_todo(todo_id)
    except TodoNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Todo {todo_id} not found") from e


@router.post("/{todo_id}/complete", response_model=Todo)
async def complete_todo(request: Request, todo_id: str = Path(..., description="Todo ID")) -> Todo:
    """Mark a todo as completed."""
    db: TodoDatabase = request.app.state.db

    try:
        completed_todo = await db.complete_todo(todo_id)
        completed_todo["id"] = str(completed_todo["id"])
        return Todo(**completed_todo)
    except TodoNotFoundError as e:
        raise HTTPException(status_code=404, detail=f"Todo {todo_id} not found") from e
