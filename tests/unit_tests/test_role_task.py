"""Tests for role-task association API."""
import pytest
from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from src.models import Base
from src.models.task import Task
from src.models.role import Role
from src.models.role_task import RoleTask


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
async def session():
    """In-memory SQLite session for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_maker() as s:
        yield s

    await engine.dispose()


@pytest.fixture
async def setup_data(session: AsyncSession):
    """Create a role and a task for testing."""
    role = Role(name="test-role", description="Test role")
    task = Task(title="Test Task", description="A test task", status="PENDING", priority="MEDIUM")
    session.add(role)
    session.add(task)
    await session.commit()
    await session.refresh(role)
    await session.refresh(task)
    return role, task


# ── model tests ───────────────────────────────────────────────────────────────

class TestRoleTaskModel:
    """Unit tests for RoleTask model."""

    @pytest.mark.asyncio
    async def test_role_task_table_registered(self):
        """Verify role_tasks table is in Base metadata."""
        from src.models import Base
        assert "role_tasks" in Base.metadata.tables

    @pytest.mark.asyncio
    async def test_assign_role_to_task(self, session: AsyncSession, setup_data):
        """Test assigning a role to a task via service."""
        from src.services.role_task import RoleTaskService

        role, task = setup_data
        svc = RoleTaskService(session)

        r, t, assigned_at = await svc.assign_role_to_task(task.id, role.id)

        assert r.id == role.id
        assert t.id == task.id
        assert assigned_at is not None

    @pytest.mark.asyncio
    async def test_assign_duplicate_raises(self, session: AsyncSession, setup_data):
        """Assigning the same role twice must raise ValueError."""
        from src.services.role_task import RoleTaskService

        role, task = setup_data
        svc = RoleTaskService(session)

        await svc.assign_role_to_task(task.id, role.id)
        with pytest.raises(ValueError, match="already assigned"):
            await svc.assign_role_to_task(task.id, role.id)

    @pytest.mark.asyncio
    async def test_assign_nonexistent_task(self, session: AsyncSession, setup_data):
        """Assigning to a non-existent task raises ValueError."""
        from src.services.role_task import RoleTaskService

        role, _ = setup_data
        svc = RoleTaskService(session)

        with pytest.raises(ValueError, match="not found"):
            await svc.assign_role_to_task(9999, role.id)

    @pytest.mark.asyncio
    async def test_assign_nonexistent_role(self, session: AsyncSession, setup_data):
        """Assigning a non-existent role raises ValueError."""
        from src.services.role_task import RoleTaskService

        _, task = setup_data
        svc = RoleTaskService(session)

        with pytest.raises(ValueError, match="not found"):
            await svc.assign_role_to_task(task.id, 9999)

    @pytest.mark.asyncio
    async def test_unassign_role(self, session: AsyncSession, setup_data):
        """Test unassigning a role from a task."""
        from src.services.role_task import RoleTaskService

        role, task = setup_data
        svc = RoleTaskService(session)

        await svc.assign_role_to_task(task.id, role.id)
        ok = await svc.unassign_role_from_task(task.id, role.id)

        assert ok is True

    @pytest.mark.asyncio
    async def test_unassign_not_assigned_raises(self, session: AsyncSession, setup_data):
        """Unassigning a role that wasn't assigned raises ValueError."""
        from src.services.role_task import RoleTaskService

        role, task = setup_data
        svc = RoleTaskService(session)

        with pytest.raises(ValueError, match="not assigned"):
            await svc.unassign_role_from_task(task.id, role.id)

    @pytest.mark.asyncio
    async def test_get_tasks_by_role(self, session: AsyncSession, setup_data):
        """Test retrieving all tasks for a role."""
        from src.services.role_task import RoleTaskService

        role, task = setup_data
        svc = RoleTaskService(session)

        await svc.assign_role_to_task(task.id, role.id)
        r2, tasks, total = await svc.get_tasks_by_role(role.id)

        assert r2.id == role.id
        assert total == 1
        assert len(tasks) == 1
        assert tasks[0].id == task.id

    @pytest.mark.asyncio
    async def test_get_tasks_by_role_empty(self, session: AsyncSession, setup_data):
        """A role with no tasks returns empty list."""
        from src.services.role_task import RoleTaskService

        role, _ = setup_data
        svc = RoleTaskService(session)

        r2, tasks, total = await svc.get_tasks_by_role(role.id)

        assert total == 0
        assert tasks == []

    @pytest.mark.asyncio
    async def test_get_tasks_by_nonexistent_role(self, session: AsyncSession, setup_data):
        """Getting tasks for a non-existent role raises ValueError."""
        from src.services.role_task import RoleTaskService

        svc = RoleTaskService(session)
        with pytest.raises(ValueError, match="not found"):
            await svc.get_tasks_by_role(9999)


# ── schema tests ───────────────────────────────────────────────────────────────

class TestRoleTaskSchemas:
    """Schema validation tests."""

    def test_role_assign_request_valid(self):
        from src.schemas.role_task import RoleAssignRequest
        req = RoleAssignRequest(role_id=1)
        assert req.role_id == 1



    def test_role_assign_response(self):
        from src.schemas.role_task import RoleAssignResponse
        resp = RoleAssignResponse(role_id=1, task_id=2, assigned_at=datetime.now())
        assert resp.role_id == 1
        assert resp.task_id == 2

    def test_task_brief_response(self):
        from src.schemas.role_task import TaskBriefResponse
        now = datetime.now()
        t = TaskBriefResponse(
            id=1, title="Test", status="PENDING", priority="MEDIUM",
            created_at=now, updated_at=now
        )
        assert t.title == "Test"

    def test_role_tasks_response(self):
        from src.schemas.role_task import RoleTasksResponse, TaskBriefResponse
        now = datetime.now()
        tasks = [
            TaskBriefResponse(id=1, title="T1", status="PENDING", priority="MEDIUM",
                              created_at=now, updated_at=now)
        ]
        resp = RoleTasksResponse(role_id=5, tasks=tasks, total=1)
        assert resp.role_id == 5
        assert len(resp.tasks) == 1
