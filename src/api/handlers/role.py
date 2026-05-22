"""Role CRUD API handler."""
import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.schemas.role import (
    PaginatedRolesResponse,
    RoleCreate,
    RoleResponse,
    RoleUpdate,
)
from src.services.role import RoleService
from src.storage.database import get_session

router = APIRouter(prefix="/roles", tags=["roles"])


async def get_role_service(session: AsyncSession = Depends(get_session)) -> RoleService:
    """Dependency: get RoleService."""
    return RoleService(session)


@router.post("", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    data: RoleCreate,
    service: RoleService = Depends(get_role_service),
) -> RoleResponse:
    """Create a new role."""
    try:
        role = await service.create(data)
        return RoleResponse.model_validate(role)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e


@router.get("", response_model=PaginatedRolesResponse)
async def list_roles(
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    service: RoleService = Depends(get_role_service),
) -> PaginatedRolesResponse:
    """List roles with pagination."""
    items, total = await service.list_roles(page=page, page_size=page_size)
    pages = math.ceil(total / page_size) if total > 0 else 0
    return PaginatedRolesResponse(
        items=[RoleResponse.model_validate(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/{role_id}", response_model=RoleResponse)
async def get_role(
    role_id: int,
    service: RoleService = Depends(get_role_service),
) -> RoleResponse:
    """Get a role by ID."""
    role = await service.get_by_id(role_id)
    if not role:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return RoleResponse.model_validate(role)


@router.put("/{role_id}", response_model=RoleResponse)
async def update_role(
    role_id: int,
    data: RoleUpdate,
    service: RoleService = Depends(get_role_service),
) -> RoleResponse:
    """Update a role."""
    try:
        role = await service.update(role_id, data)
        return RoleResponse.model_validate(role)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from e


@router.delete("/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: int,
    hard: Annotated[bool, Query(description="If true, permanently delete")] = False,
    service: RoleService = Depends(get_role_service),
) -> None:
    """Delete a role (soft-delete by default)."""
    try:
        await service.delete(role_id, hard=hard)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
