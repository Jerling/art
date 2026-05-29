"""Task CRUD API handler."""
import logging
import math
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.schemas.task import (
    PaginatedTasksResponse,
    TaskCreate,
    TaskResponse,
    TaskStatus,
    TaskStatusUpdate,
    TaskUpdate,
)
from src.services.task import TaskService
from src.storage.database import get_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def _save_push_log(session, log) -> None:
    """Save a push log record (helper for on_log callback)."""
    from src.storage.wechat_push_log import WeChatPushLogStore

    await WeChatPushLogStore(session).save(log)


async def get_task_service(session: AsyncSession = Depends(get_session)) -> TaskService:
    """Dependency: get TaskService."""
    return TaskService(session)


def _task_to_response(task, role_ids: list[int]) -> TaskResponse:
    """Build a TaskResponse from a Task model instance."""
    return TaskResponse(
        id=task.id,
        title=task.title,
        description=task.description,
        status=TaskStatus(task.status),
        priority=task.priority,  # type: ignore[arg] — Pydantic coerces str→TaskPriority
        estimated_hours=task.estimated_hours,
        created_at=task.created_at,
        updated_at=task.updated_at,
        role_ids=role_ids,
        openid=task.openid,
    )


@router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    data: TaskCreate,
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    """Create a new task (optionally assigning roles).

    If ``data.openid`` is set, a WeChat customer-service text message
    is pushed to that OpenID after the task is created successfully.
    The push is best-effort — failure does not affect the 201 response.
    """
    try:
        task = await service.create(data)
        role_ids = await service._get_role_ids_for_task(task.id)
        response = _task_to_response(task, role_ids)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    # Best-effort WeChat push notification
    if data.openid:
        from src.services.wechat_push import PushType, WeChatPushService

        push_service = WeChatPushService(
            on_log=lambda log: _save_push_log(service.session, log),
        )
        try:
            hours_str = f"{task.estimated_hours}h" if task.estimated_hours else "未估算"
            push_text = (
                f"✅ 任务已创建："
                f"「{task.title}」"
                f"\n优先级 {task.priority}"
                f"，预计 {hours_str}"
            )
            push_result = await push_service.send_text(
                openid=data.openid,
                text=push_text,
                push_type=PushType.TASK_CREATED,
                task_id=task.id,
            )
            if not push_result.success:
                logger.warning(
                    "[task_create] WeChat push failed for openid=%s task_id=%d: %s",
                    data.openid,
                    task.id,
                    push_result.error,
                )
        except Exception as exc:
            logger.error(
                "[task_create] WeChat push error for openid=%s task_id=%d: %s",
                data.openid,
                task.id,
                exc,
            )
        finally:
            await push_service.close()

    # Best-effort WeChat push to assigned roles
    if role_ids:
        await _notify_role_assignments(task, role_ids, service)

    return response


@router.get("", response_model=PaginatedTasksResponse)
async def list_tasks(
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    role_id: Annotated[int | None, Query(description="Filter by role ID")] = None,
    status: Annotated[TaskStatus | None, Query(description="Filter by status")] = None,
    service: TaskService = Depends(get_task_service),
) -> PaginatedTasksResponse:
    """List tasks with pagination and optional filters."""
    items, total = await service.list_tasks(
        page=page, page_size=page_size, role_id=role_id, status=status
    )
    pages = math.ceil(total / page_size) if total > 0 else 0
    task_responses = []
    for task in items:
        role_ids = await service._get_role_ids_for_task(task.id)
        task_responses.append(_task_to_response(task, role_ids))
    return PaginatedTasksResponse(
        items=task_responses,
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    """Get a task by ID."""
    task = await service.get_by_id(task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    role_ids = await service._get_role_ids_for_task(task.id)
    return _task_to_response(task, role_ids)


@router.put("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    data: TaskUpdate,
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    """Update a task (partial update).

    Assigned roles change notification:
    Sends WeChat push to all newly assigned role openids.
    """
    try:
        task = await service.update(task_id, data)
        role_ids = await service._get_role_ids_for_task(task.id)
        response = _task_to_response(task, role_ids)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from e

    # Best-effort WeChat push to assigned roles when role_ids changed
    if data.role_ids is not None and role_ids:
        await _notify_role_assignments(task, role_ids, service)

    return response


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    hard: Annotated[bool, Query(description="If true, permanently delete")] = False,
    service: TaskService = Depends(get_task_service),
) -> None:
    """Delete a task (soft-delete by default)."""
    try:
        await service.delete(task_id, hard=hard)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


def _build_status_push_text(task, old_status: str) -> str:
    """Build WeChat push text for a task status change."""
    status_labels = {
        "PENDING": "待处理",
        "IN_PROGRESS": "进行中",
        "DONE": "已完成",
        "CANCELLED": "已取消",
    }
    old_label = status_labels.get(old_status, old_status)
    new_label = status_labels.get(task.status, task.status)
    return (
        f"📋 任务状态更新："
        f"「{task.title}」"
        f"\n{old_label} → {new_label}"
    )


async def _notify_role_assignments(
    task,
    role_ids: list[int],
    service: TaskService,
) -> None:
    """Send WeChat push to newly assigned roles with push log recording."""
    if not role_ids:
        return

    from src.models.role import Role
    from src.services.wechat_push import PushType, WeChatPushService

    # Load roles to get their openids and names
    for rid in role_ids:
        role = await service.session.get(Role, rid)
        if not role or not role.openid:
            continue

        push_service = WeChatPushService(
            on_log=lambda log, s=service.session: _save_push_log(s, log),
        )
        try:
            result = await push_service.send_task_assigned(
                openid=role.openid,
                task_id=task.id,
                task_title=task.title,
                role_name=role.name,
            )
            if not result.success:
                logger.warning(
                    "[task_notify] Push to role %s (openid=%s) for task_id=%d failed: %s",
                    role.name,
                    role.openid,
                    task.id,
                    result.error,
                )
        except Exception as exc:
            logger.error(
                "[task_notify] Push to role %s (openid=%s) for task_id=%d error: %s",
                role.name,
                role.openid,
                task.id,
                exc,
            )
        finally:
            await push_service.close()


@router.patch("/{task_id}/status", response_model=TaskResponse)
async def update_task_status(
    task_id: int,
    data: TaskStatusUpdate,
    service: TaskService = Depends(get_task_service),
) -> TaskResponse:
    """Transition a task's status (PENDING→IN_PROGRESS→DONE, or CANCELLED).

    Sends a WeChat push notification to the task creator (openid) on status change.
    """
    # Fetch task first for push notification (need old status and openid)
    task_before = await service.get_by_id(task_id)
    if not task_before:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task with id {task_id} not found",
        )
    old_status = task_before.status

    try:
        task = await service.update_status(task_id, data)
        role_ids = await service._get_role_ids_for_task(task.id)
        response = _task_to_response(task, role_ids)
    except ValueError as e:
        msg = str(e)
        if "not found" in msg.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=msg) from e
        if "invalid" in msg.lower() or "transition" in msg.lower():
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=msg) from e
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=msg) from e

    # Best-effort WeChat push notification to creator on status change
    if task_before.openid:
        from src.services.wechat_push import PushType, WeChatPushService

        push_service = WeChatPushService(
            on_log=lambda log: _save_push_log(service.session, log),
        )
        try:
            # Use dedicated methods for specific notification types
            if data.status.value == "DONE":
                push_result = await push_service.send_task_completed(
                    openid=task_before.openid,
                    task_id=task.id,
                    task_title=task.title,
                )
            else:
                push_text = _build_status_push_text(task, old_status)
                push_result = await push_service.send_text(
                    openid=task_before.openid,
                    text=push_text,
                    push_type=PushType.TASK_STATUS_CHANGED,
                    task_id=task.id,
                )
            if not push_result.success:
                logger.warning(
                    "[task_status] WeChat push failed for openid=%s task_id=%d: %s",
                    task_before.openid,
                    task_id,
                    push_result.error,
                )
        except Exception as exc:
            logger.error(
                "[task_status] WeChat push error for openid=%s task_id=%d: %s",
                task_before.openid,
                task_id,
                exc,
            )
        finally:
            await push_service.close()

    return response
