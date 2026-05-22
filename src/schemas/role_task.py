"""Pydantic schemas for role-task association."""
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field


class RoleAssignRequest(BaseModel):
    """Request body for assigning a role to a task."""

    role_id: int = Field(..., description="ID of the role to assign")


class RoleAssignResponse(BaseModel):
    """Response after assigning a role to a task."""

    role_id: int
    task_id: int
    assigned_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TaskBriefResponse(BaseModel):
    """Brief task info returned when listing tasks by role."""

    id: int
    title: str
    status: str
    priority: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class RoleTasksResponse(BaseModel):
    """Response listing all tasks for a role."""

    role_id: int
    tasks: list[TaskBriefResponse]
    total: int
