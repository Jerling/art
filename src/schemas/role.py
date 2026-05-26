"""Pydantic schemas for Role CRUD."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RoleCreate(BaseModel):
    """Schema for creating a role."""

    name: str = Field(..., min_length=1, max_length=100, description="Role name (unique)")
    description: str | None = Field(None, max_length=500, description="Optional description")


class RoleUpdate(BaseModel):
    """Schema for updating a role."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)


class RoleResponse(BaseModel):
    """Schema for a role in responses."""

    id: int
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class PaginatedRolesResponse(BaseModel):
    """Paginated list of roles."""

    items: list[RoleResponse]
    total: int
    page: int
    page_size: int
    pages: int
