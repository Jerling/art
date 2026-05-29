"""Service layer for Task CRUD operations."""
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.role import Role
from src.models.role_task import RoleTask
from src.models.task import Task
from src.schemas.task import (
    VALID_TRANSITIONS,
    TaskCreate,
    TaskStatus,
    TaskStatusUpdate,
    TaskUpdate,
)

UTC = UTC


def _naive_dt() -> datetime:
    """Return UTC naive datetime for DB compatibility."""
    return datetime.now(UTC).replace(tzinfo=None)


class TaskService:
    """CRUD operations for Task."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── internal helpers ──────────────────────────────────────────────────────

    async def _get_role_ids_for_task(self, task_id: int) -> list[int]:
        """Return list of role_ids assigned to a task."""
        result = await self.session.execute(
            select(RoleTask.role_id).where(RoleTask.task_id == task_id)
        )
        return [row[0] for row in result.all()]

    async def _set_role_ids(self, task_id: int, role_ids: list[int]) -> None:
        """Replace all role assignments for a task."""
        # Remove existing assignments
        await self.session.execute(
            delete(RoleTask).where(RoleTask.task_id == task_id)
        )
        # Add new ones
        for rid in role_ids:
            self.session.add(RoleTask(role_id=rid, task_id=task_id, assigned_at=_naive_dt()))

    async def _validate_role_ids(self, role_ids: list[int]) -> None:
        """Verify all role_ids exist and are not soft-deleted."""
        if not role_ids:
            return
        result = await self.session.execute(
            select(Role.id).where(Role.id.in_(role_ids), Role.deleted_at.is_(None))
        )
        found = {row[0] for row in result.all()}
        missing = set(role_ids) - found
        if missing:
            raise ValueError(f"Role(s) not found: {', '.join(map(str, sorted(missing)))}")

    # ── public CRUD ───────────────────────────────────────────────────────────

    async def create(self, data: TaskCreate) -> Task:
        """Create a new task, optionally assigning roles."""
        if data.role_ids:
            await self._validate_role_ids(data.role_ids)

        task = Task(
            title=data.title,
            description=data.description,
            priority=data.priority.value,
            estimated_hours=data.estimated_hours,
            openid=data.openid,
        )
        self.session.add(task)
        try:
            await self.session.commit()
            await self.session.refresh(task)
        except IntegrityError:
            await self.session.rollback()
            raise ValueError("Failed to create task due to constraint violation")

        if data.role_ids:
            await self._set_role_ids(task.id, data.role_ids)
            await self.session.commit()
            await self.session.refresh(task)

        return task

    async def get_by_id(self, task_id: int) -> Task | None:
        """Get a task by ID (excludes soft-deleted)."""
        result = await self.session.execute(
            select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        page: int = 1,
        page_size: int = 20,
        role_id: int | None = None,
        status: TaskStatus | None = None,
    ) -> tuple[list[Task], int]:
        """List tasks with pagination, optionally filtered by role_id or status."""
        base = select(Task).where(Task.deleted_at.is_(None))

        if status is not None:
            base = base.where(Task.status == status.value)

        if role_id is not None:
            # Filter tasks that have this role assigned
            base = base.join(RoleTask, RoleTask.task_id == Task.id).where(
                RoleTask.role_id == role_id
            )

        # Total count
        count_query = (
            select(func.count(Task.id))
            .where(Task.deleted_at.is_(None))
        )
        if status is not None:
            count_query = count_query.where(Task.status == status.value)
        if role_id is not None:
            count_query = count_query.join(RoleTask, RoleTask.task_id == Task.id).where(
                RoleTask.role_id == role_id
            )
        count_result = await self.session.execute(count_query)
        total = count_result.scalar_one()

        # Paginated items
        offset = (page - 1) * page_size
        result = await self.session.execute(
            base.order_by(Task.id.desc()).offset(offset).limit(page_size)
        )
        items = list(result.scalars().all())
        return items, total

    async def update(self, task_id: int, data: TaskUpdate) -> Task:
        """Update a task. Returns updated task or raises ValueError if not found."""
        task = await self.get_by_id(task_id)
        if not task:
            raise ValueError(f"Task with id {task_id} not found")

        if data.role_ids is not None:
            await self._validate_role_ids(data.role_ids)

        if data.title is not None:
            task.title = data.title
        if data.description is not None:
            task.description = data.description
        if data.priority is not None:
            task.priority = data.priority.value
        if data.estimated_hours is not None:
            task.estimated_hours = data.estimated_hours
        task.updated_at = _naive_dt()

        try:
            await self.session.commit()
            await self.session.refresh(task)
        except IntegrityError:
            await self.session.rollback()
            raise ValueError("Failed to update task due to constraint violation")

        if data.role_ids is not None:
            await self._set_role_ids(task_id, data.role_ids)
            await self.session.commit()
            await self.session.refresh(task)

        return task

    async def delete(self, task_id: int, hard: bool = False) -> bool:
        """Delete a task. Soft-delete by default, hard-delete if hard=True."""
        task = await self.get_by_id(task_id)
        if not task:
            raise ValueError(f"Task with id {task_id} not found")

        if hard:
            # Remove role assignments first
            await self.session.execute(
                delete(RoleTask).where(RoleTask.task_id == task_id)
            )
            await self.session.delete(task)
        else:
            task.deleted_at = _naive_dt()
        await self.session.commit()
        return True

    async def update_status(self, task_id: int, data: TaskStatusUpdate) -> Task:
        """Transition task status. Validates against VALID_TRANSITIONS."""
        task = await self.get_by_id(task_id)
        if not task:
            raise ValueError(f"Task with id {task_id} not found")

        current = TaskStatus(task.status)
        target = data.status

        if target not in VALID_TRANSITIONS.get(current, set()):
            allowed = VALID_TRANSITIONS.get(current, set())
            allowed_str = ", ".join(s.value for s in allowed) if allowed else "none"
            raise ValueError(
                f"Invalid status transition from '{current.value}' to '{target.value}'. "
                f"Allowed transitions: {allowed_str}"
            )

        task.status = target.value
        task.updated_at = _naive_dt()
        await self.session.commit()
        await self.session.refresh(task)
        return task
