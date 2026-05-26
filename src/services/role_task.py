"""Service layer for role-task association operations."""
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.role import Role
from src.models.task import Task


class RoleTaskService:
    """Many-to-many association between roles and tasks."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def assign_role_to_task(self, task_id: int, role_id: int) -> tuple[Role, Task, datetime]:
        """Assign a role to a task. Returns (role, task) or raises ValueError."""
        # Verify task exists
        task_result = await self.session.execute(
            select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
        )
        task = task_result.scalar_one_or_none()
        if not task:
            raise ValueError(f"Task with id {task_id} not found")

        # Verify role exists
        role_result = await self.session.execute(
            select(Role).where(Role.id == role_id, Role.deleted_at.is_(None))
        )
        role = role_result.scalar_one_or_none()
        if not role:
            raise ValueError(f"Role with id {role_id} not found")

        # Try to insert the junction record
        # role_tasks table: role_id (FK), task_id (FK), assigned_at
        # We use raw SQL to insert into the junction table directly
        from sqlalchemy import insert

        from src.models import Base

        # Get the role_tasks table from Base metadata
        role_tasks_table = Base.metadata.tables["role_tasks"]

        stmt = insert(role_tasks_table).values(
            role_id=role_id, task_id=task_id, assigned_at=datetime.now(UTC)
        )
        try:
            await self.session.execute(stmt)
            await self.session.commit()
        except IntegrityError:
            await self.session.rollback()
            raise ValueError(
                f"Role {role_id} is already assigned to task {task_id}"
            )

        assigned_at = datetime.now(UTC)
        return role, task, assigned_at

    async def unassign_role_from_task(self, task_id: int, role_id: int) -> bool:
        """Remove a role assignment from a task. Returns True or raises ValueError."""
        # Verify task exists
        task_result = await self.session.execute(
            select(Task).where(Task.id == task_id, Task.deleted_at.is_(None))
        )
        task = task_result.scalar_one_or_none()
        if not task:
            raise ValueError(f"Task with id {task_id} not found")

        # Verify role exists
        role_result = await self.session.execute(
            select(Role).where(Role.id == role_id, Role.deleted_at.is_(None))
        )
        role = role_result.scalar_one_or_none()
        if not role:
            raise ValueError(f"Role with id {role_id} not found")

        from src.models import Base

        role_tasks_table = Base.metadata.tables["role_tasks"]

        # Check if assignment exists first
        check_stmt = select(role_tasks_table).where(
            role_tasks_table.c.role_id == role_id,
            role_tasks_table.c.task_id == task_id,
        )
        check_result = await self.session.execute(check_stmt)
        if check_result.first() is None:
            raise ValueError(
                f"Role {role_id} is not assigned to task {task_id}"
            )

        stmt = delete(role_tasks_table).where(
            role_tasks_table.c.role_id == role_id,
            role_tasks_table.c.task_id == task_id,
        )
        await self.session.execute(stmt)
        await self.session.commit()

        return True

    async def get_tasks_by_role(self, role_id: int) -> tuple[Role, list[Task], int]:
        """Get all tasks for a role. Returns (role, tasks, total)."""
        # Verify role exists
        role_result = await self.session.execute(
            select(Role).where(Role.id == role_id, Role.deleted_at.is_(None))
        )
        role = role_result.scalar_one_or_none()
        if not role:
            raise ValueError(f"Role with id {role_id} not found")

        from src.models import Base

        role_tasks_table = Base.metadata.tables["role_tasks"]

        # Count total
        count_stmt = (
            select(role_tasks_table.c.task_id)
            .where(role_tasks_table.c.role_id == role_id)
        )
        count_result = await self.session.execute(count_stmt)
        total = len(count_result.all())

        # Get tasks with this role
        from sqlalchemy import select as sa_select

        tasks_stmt = (
            sa_select(Task)
            .join(role_tasks_table, role_tasks_table.c.task_id == Task.id)
            .where(
                role_tasks_table.c.role_id == role_id,
                Task.deleted_at.is_(None),
            )
            .order_by(Task.id)
        )
        tasks_result = await self.session.execute(tasks_stmt)
        tasks = list(tasks_result.scalars().all())

        return role, tasks, total
