"""Role-Task association API handlers."""
from collections.abc import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.schemas.role_task import (
    RoleAssignRequest,
    RoleAssignResponse,
    RoleTasksResponse,
    TaskBriefResponse,
)
from src.services.role_task import RoleTaskService
from src.storage.database import async_session_maker


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency: get async DB session."""
    async with async_session_maker() as session:
        yield session


async def get_role_task_service(
    session: AsyncSession = Depends(get_session),
) -> RoleTaskService:
    """Dependency: get RoleTaskService."""
    return RoleTaskService(session)


# ── Router for /tasks/{id}/roles ─────────────────────────────────────────────

task_roles_router = APIRouter(prefix="/tasks", tags=["task-roles"])


@task_roles_router.post(
    "/{task_id}/roles",
    response_model=RoleAssignResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_role_to_task(
    task_id: int,
    data: RoleAssignRequest,
    service: RoleTaskService = Depends(get_role_task_service),
) -> RoleAssignResponse:
    """Assign a role to a task."""
    try:
        role, task, assigned_at = await service.assign_role_to_task(task_id, data.role_id)
        return RoleAssignResponse(
            role_id=role.id,
            task_id=task.id,
            assigned_at=assigned_at,
        )
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        if "already assigned" in msg.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e


@task_roles_router.delete(
    "/{task_id}/roles/{role_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unassign_role_from_task(
    task_id: int,
    role_id: int,
    service: RoleTaskService = Depends(get_role_task_service),
) -> None:
    """Remove a role assignment from a task."""
    try:
        await service.unassign_role_from_task(task_id, role_id)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        if "not assigned" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg) from e


# ── Router for /roles/{id}/tasks ─────────────────────────────────────────────

role_tasks_router = APIRouter(prefix="/roles", tags=["role-tasks"])


@role_tasks_router.get(
    "/{role_id}/tasks",
    response_model=RoleTasksResponse,
)
async def get_tasks_by_role(
    role_id: int,
    service: RoleTaskService = Depends(get_role_task_service),
) -> RoleTasksResponse:
    """Get all tasks assigned to a role."""
    try:
        role, tasks, total = await service.get_tasks_by_role(role_id)
        return RoleTasksResponse(
            role_id=role.id,
            tasks=[TaskBriefResponse.model_validate(t) for t in tasks],
            total=total,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
