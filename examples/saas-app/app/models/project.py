"""Project and agent models."""

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectStatus(str, Enum):
    """Project status options."""

    PLANNING = "planning"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ProjectBase(BaseModel):
    """Base project model."""

    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    status: ProjectStatus = ProjectStatus.PLANNING
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    metadata: Optional[dict[str, Any]] = Field(default_factory=dict)


class ProjectCreate(ProjectBase):
    """Model for creating a project."""

    pass


class ProjectUpdate(BaseModel):
    """Model for updating a project."""

    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    status: Optional[ProjectStatus] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    metadata: Optional[dict[str, Any]] = None


class Project(ProjectBase):
    """Complete project model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class TaskBase(BaseModel):
    """Base agent model."""

    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    assigned_to: Optional[UUID] = None
    due_date: Optional[date] = None
    priority: int = Field(default=0, ge=0, le=5)


class AgentCreate(TaskBase):
    """Model for creating a agent."""

    pass


class AgentUpdate(BaseModel):
    """Model for updating a agent."""

    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    assigned_to: Optional[UUID] = None
    is_completed: Optional[bool] = None
    due_date: Optional[date] = None
    priority: Optional[int] = Field(None, ge=0, le=5)


class Agent(TaskBase):
    """Complete agent model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    is_completed: bool
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = None


class ProjectWithTasks(Project):
    """Project model with agents."""

    agents: list[Agent] = []
    task_count: int = 0
    completed_task_count: int = 0


class Comment(BaseModel):
    """Agent comment model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    author_id: UUID
    content: str
    created_at: datetime
    updated_at: datetime
    edited_at: Optional[datetime] = None
