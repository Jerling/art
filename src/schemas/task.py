"""Pydantic schemas for Task CRUD."""
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(str, Enum):
    """Valid task status values."""

    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    CANCELLED = "CANCELLED"


class TaskPriority(str, Enum):
    """Valid task priority values."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


# Valid status transitions
VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PENDING: {TaskStatus.IN_PROGRESS, TaskStatus.CANCELLED},
    TaskStatus.IN_PROGRESS: {TaskStatus.DONE, TaskStatus.CANCELLED},
    TaskStatus.DONE: set(),  # Terminal state
    TaskStatus.CANCELLED: set(),  # Terminal state
}


class TaskCreate(BaseModel):
    """Schema for creating a task."""

    title: str = Field(..., min_length=1, max_length=200, description="Task title")
    description: str | None = Field(None, max_length=2000, description="Optional description")
    priority: TaskPriority = Field(
        default=TaskPriority.MEDIUM, description="Priority level"
    )
    estimated_hours: float | None = Field(
        None, ge=0, description="Estimated hours to complete"
    )
    role_ids: list[int] | None = Field(
        default=None, description="List of role IDs to assign to this task"
    )


class TaskUpdate(BaseModel):
    """Schema for updating a task (partial update)."""

    title: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    priority: TaskPriority | None = Field(None)
    estimated_hours: float | None = Field(None, ge=0)
    role_ids: list[int] | None = Field(
        None, description="Replacement role assignment list"
    )


class TaskStatusUpdate(BaseModel):
    """Schema for status transition."""

    status: TaskStatus = Field(..., description="New status")


class TaskResponse(BaseModel):
    """Schema for a task in responses."""

    id: int
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    estimated_hours: float | None
    created_at: datetime
    updated_at: datetime
    role_ids: list[int] = Field(default_factory=list, description="Assigned role IDs")

    model_config = ConfigDict(from_attributes=True)


class PaginatedTasksResponse(BaseModel):
    """Paginated list of tasks."""

    items: list[TaskResponse]
    total: int
    page: int
    page_size: int
    pages: int
