"""Unit tests for Tasks CRUD API.

Run with:
  pytest tests/unit_tests/test_tasks.py -v --cov=src --cov-report=term-missing
"""
from __future__ import annotations

import math
import sys
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

sys.path.insert(0, sys.path[0])

from src.schemas.task import (
    PaginatedTasksResponse,
    TaskCreate,
    TaskPriority,
    TaskResponse,
    TaskStatus,
    TaskStatusUpdate,
    TaskUpdate,
    VALID_TRANSITIONS,
)


# ─────────────────────────────────────────────────────────────────────────────
# Schema validation tests
# ─────────────────────────────────────────────────────────────────────────────
class TestTaskCreateSchema:
    def test_valid_task_create_minimal(self):
        data = TaskCreate(title="Implement login")
        assert data.title == "Implement login"
        assert data.description is None
        assert data.priority == TaskPriority.MEDIUM
        assert data.estimated_hours is None
        assert data.role_ids is None

    def test_valid_task_create_full(self):
        data = TaskCreate(
            title="Implement login",
            description="Add OAuth2 login flow",
            priority=TaskPriority.HIGH,
            estimated_hours=4.5,
            role_ids=[1, 2],
        )
        assert data.title == "Implement login"
        assert data.description == "Add OAuth2 login flow"
        assert data.priority == TaskPriority.HIGH
        assert data.estimated_hours == 4.5
        assert data.role_ids == [1, 2]

    def test_title_required(self):
        with pytest.raises(ValidationError) as exc_info:
            TaskCreate(title="")
        assert "title" in str(exc_info.value)

    def test_title_max_length(self):
        with pytest.raises(ValidationError):
            TaskCreate(title="x" * 201)

    def test_description_max_length(self):
        with pytest.raises(ValidationError):
            TaskCreate(title="Valid", description="x" * 2001)

    def test_estimated_hours_non_negative(self):
        with pytest.raises(ValidationError):
            TaskCreate(title="Task", estimated_hours=-1.0)


class TestTaskUpdateSchema:
    def test_empty_update_allowed(self):
        data = TaskUpdate()
        assert data.title is None
        assert data.description is None
        assert data.priority is None
        assert data.estimated_hours is None
        assert data.role_ids is None

    def test_partial_update_title(self):
        data = TaskUpdate(title="New title")
        assert data.title == "New title"

    def test_partial_update_priority(self):
        data = TaskUpdate(priority=TaskPriority.URGENT)
        assert data.priority == TaskPriority.URGENT

    def test_title_min_length_when_provided(self):
        with pytest.raises(ValidationError):
            TaskUpdate(title="")


class TestTaskStatusUpdateSchema:
    def test_valid_status_update(self):
        data = TaskStatusUpdate(status=TaskStatus.IN_PROGRESS)
        assert data.status == TaskStatus.IN_PROGRESS

    def test_all_statuses_valid(self):
        for status in TaskStatus:
            data = TaskStatusUpdate(status=status)
            assert data.status == status


class TestTaskResponseSchema:
    def test_from_attributes(self):
        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.title = "Test Task"
        mock_task.description = "Description"
        mock_task.status = "PENDING"
        mock_task.priority = "HIGH"
        mock_task.estimated_hours = 3.0
        mock_task.created_at = datetime(2026, 1, 1, 12, 0, 0)
        mock_task.updated_at = datetime(2026, 1, 2, 12, 0, 0)

        response = TaskResponse(
            id=1,
            title="Test Task",
            description="Description",
            status=TaskStatus.PENDING,
            priority=TaskPriority.HIGH,
            estimated_hours=3.0,
            created_at=datetime(2026, 1, 1, 12, 0, 0),
            updated_at=datetime(2026, 1, 2, 12, 0, 0),
            role_ids=[1, 2],
        )
        assert response.id == 1
        assert response.status == TaskStatus.PENDING
        assert response.priority == TaskPriority.HIGH


class TestPaginatedTasksResponse:
    def test_pagination_fields(self):
        response = PaginatedTasksResponse(
            items=[],
            total=50,
            page=2,
            page_size=10,
            pages=5,
        )
        assert response.total == 50
        assert response.page == 2
        assert response.pages == 5


class TestVALID_TRANSITIONS:
    """Test that status transition map is correct."""

    def test_pending_transitions(self):
        assert TaskStatus.IN_PROGRESS in VALID_TRANSITIONS[TaskStatus.PENDING]
        assert TaskStatus.CANCELLED in VALID_TRANSITIONS[TaskStatus.PENDING]
        assert TaskStatus.DONE not in VALID_TRANSITIONS[TaskStatus.PENDING]

    def test_in_progress_transitions(self):
        assert TaskStatus.DONE in VALID_TRANSITIONS[TaskStatus.IN_PROGRESS]
        assert TaskStatus.CANCELLED in VALID_TRANSITIONS[TaskStatus.IN_PROGRESS]
        assert TaskStatus.PENDING not in VALID_TRANSITIONS[TaskStatus.IN_PROGRESS]

    def test_done_is_terminal(self):
        assert VALID_TRANSITIONS[TaskStatus.DONE] == set()

    def test_cancelled_is_terminal(self):
        assert VALID_TRANSITIONS[TaskStatus.CANCELLED] == set()


# ─────────────────────────────────────────────────────────────────────────────
# Service layer tests
# ─────────────────────────────────────────────────────────────────────────────
class TestTaskServiceValidation:
    """Test TaskService methods with mocked async session."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    # ── create ────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_task_success(self, mock_session):
        from src.services.task import TaskService

        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.title = "Test Task"
        mock_task.description = None
        mock_task.status = "PENDING"
        mock_task.priority = "MEDIUM"
        mock_task.estimated_hours = None
        mock_task.deleted_at = None
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.updated_at = datetime.now(timezone.utc)

        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        # Mock _get_role_ids_for_task
        with patch("src.services.task.Task") as MockTask:
            MockTask.return_value = mock_task
            service = TaskService(mock_session)
            # No role_ids - simple create
            mock_session.execute = AsyncMock()
            result = await service.create(TaskCreate(title="Test Task"))

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called()
        assert result.title == "Test Task"

    @pytest.mark.asyncio
    async def test_create_task_with_roles_validates(self, mock_session):
        from src.services.task import TaskService

        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.title = "Test Task"

        # Mock role validation - return empty (no roles found)
        mock_result = MagicMock()
        mock_result.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with patch("src.services.task.Task") as MockTask:
            MockTask.return_value = mock_task
            service = TaskService(mock_session)
            with pytest.raises(ValueError, match="not found"):
                await service.create(TaskCreate(title="Test", role_ids=[999]))

    # ── get_by_id ────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, mock_session):
        from src.services.task import TaskService

        mock_task = MagicMock()
        mock_task.id = 1
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = TaskService(mock_session)
        result = await service.get_by_id(1)
        assert result == mock_task

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, mock_session):
        from src.services.task import TaskService

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = TaskService(mock_session)
        result = await service.get_by_id(999)
        assert result is None

    # ── list_tasks ───────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_tasks_basic(self, mock_session):
        from src.services.task import TaskService

        mock_tasks = [MagicMock(id=1), MagicMock(id=2)]

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 2

        # Mock list result
        mock_list_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_tasks
        mock_list_result.scalars.return_value.all.return_value = mock_tasks

        # Mock execute to return count first, then list
        mock_session.execute = AsyncMock(
            side_effect=[mock_count_result, mock_list_result]
        )

        service = TaskService(mock_session)
        items, total = await service.list_tasks(page=1, page_size=20)
        assert total == 2
        assert len(items) == 2

    @pytest.mark.asyncio
    async def test_list_tasks_filters_by_status(self, mock_session):
        from src.services.task import TaskService

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0
        mock_session.execute = AsyncMock(return_value=mock_count_result)

        service = TaskService(mock_session)
        await service.list_tasks(status=TaskStatus.DONE)
        # Verify execute was called (filtering is done in the query)
        assert mock_session.execute.called

    # ── update ────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_not_found(self, mock_session):
        from src.services.task import TaskService

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = TaskService(mock_session)
        with pytest.raises(ValueError, match="not found"):
            await service.update(999, TaskUpdate(title="New title"))

    # ── delete ───────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_delete_not_found(self, mock_session):
        from src.services.task import TaskService

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = TaskService(mock_session)
        with pytest.raises(ValueError, match="not found"):
            await service.delete(999)

    @pytest.mark.asyncio
    async def test_delete_soft_sets_deleted_at(self, mock_session):
        from src.services.task import TaskService

        mock_task = MagicMock()
        mock_task.deleted_at = None
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        service = TaskService(mock_session)
        result = await service.delete(1, hard=False)
        assert result is True
        assert mock_task.deleted_at is not None

    # ── update_status ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_status_valid_transition(self, mock_session):
        from src.services.task import TaskService

        mock_task = MagicMock()
        mock_task.status = "PENDING"
        mock_task.id = 1
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        service = TaskService(mock_session)
        result = await service.update_status(
            1, TaskStatusUpdate(status=TaskStatus.IN_PROGRESS)
        )
        assert mock_task.status == "IN_PROGRESS"

    @pytest.mark.asyncio
    async def test_update_status_invalid_transition(self, mock_session):
        from src.services.task import TaskService

        mock_task = MagicMock()
        mock_task.status = "DONE"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = TaskService(mock_session)
        with pytest.raises(ValueError, match="Invalid status transition"):
            await service.update_status(
                1, TaskStatusUpdate(status=TaskStatus.PENDING)
            )

    @pytest.mark.asyncio
    async def test_update_status_not_found(self, mock_session):
        from src.services.task import TaskService

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = TaskService(mock_session)
        with pytest.raises(ValueError, match="not found"):
            await service.update_status(
                999, TaskStatusUpdate(status=TaskStatus.IN_PROGRESS)
            )


# ─────────────────────────────────────────────────────────────────────────────
# Handler integration tests (mocked service)
# ─────────────────────────────────────────────────────────────────────────────
class TestTaskHandlerSchemas:
    """Test handler schema coercion without a real DB session."""

    def test_task_response_accepts_string_priority(self):
        """task.priority is str in model but TaskPriority is enum - verify coercion."""
        response = TaskResponse(
            id=1,
            title="Test",
            description=None,
            status="PENDING",  # str → TaskStatus
            priority="HIGH",  # str → TaskPriority
            estimated_hours=None,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            role_ids=[],
        )
        assert response.status == TaskStatus.PENDING
        assert response.priority == TaskPriority.HIGH

    def test_task_create_accepts_enum_priority(self):
        data = TaskCreate(title="Test", priority=TaskPriority.LOW)
        assert data.priority == TaskPriority.LOW

    def test_task_update_accepts_enum_priority(self):
        data = TaskUpdate(priority=TaskPriority.URGENT)
        assert data.priority == TaskPriority.URGENT

    def test_task_status_update_all_statuses(self):
        for s in TaskStatus:
            data = TaskStatusUpdate(status=s)
            assert data.status == s


# ─────────────────────────────────────────────────────────────────────────────
# Handler unit tests with mocked service
# ─────────────────────────────────────────────────────────────────────────────
class TestTaskHandlerMocked:
    """Test handler functions directly with mocked TaskService.

    These bypass TestClient to ensure the handler code itself is exercised.
    """

    @pytest.fixture
    def mock_service(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_create_task_handler_success(self, mock_service):
        from datetime import datetime, timezone
        from src.api.handlers.task import create_task

        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.title = "Test"
        mock_task.description = None
        mock_task.status = "PENDING"
        mock_task.priority = "MEDIUM"
        mock_task.estimated_hours = None
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.updated_at = datetime.now(timezone.utc)

        mock_service.create = AsyncMock(return_value=mock_task)
        mock_service._get_role_ids_for_task = AsyncMock(return_value=[1, 2])

        result = await create_task(
            data=TaskCreate(title="Test"),
            service=mock_service,
        )
        assert result.id == 1
        mock_service.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_task_handler_conflict(self, mock_service):
        from src.api.handlers.task import create_task

        mock_service.create = AsyncMock(side_effect=ValueError("Duplicate"))
        mock_service._get_role_ids_for_task = AsyncMock(return_value=[])

        with pytest.raises(HTTPException) as exc_info:
            await create_task(data=TaskCreate(title="Dup"), service=mock_service)
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_get_task_handler_not_found(self, mock_service):
        from src.api.handlers.task import get_task

        mock_service.get_by_id = AsyncMock(return_value=None)
        mock_service._get_role_ids_for_task = AsyncMock(return_value=[])

        with pytest.raises(HTTPException) as exc_info:
            await get_task(task_id=999, service=mock_service)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_task_handler_not_found(self, mock_service):
        from src.api.handlers.task import update_task

        mock_service.update = AsyncMock(side_effect=ValueError("Task with id 999 not found"))

        with pytest.raises(HTTPException) as exc_info:
            await update_task(task_id=999, data=TaskUpdate(title="X"), service=mock_service)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_task_handler_conflict(self, mock_service):
        from src.api.handlers.task import update_task

        mock_service.update = AsyncMock(side_effect=ValueError("Constraint violation"))

        with pytest.raises(HTTPException) as exc_info:
            await update_task(task_id=1, data=TaskUpdate(title="X"), service=mock_service)
        assert exc_info.value.status_code == 409

    @pytest.mark.asyncio
    async def test_delete_task_handler_not_found(self, mock_service):
        from src.api.handlers.task import delete_task

        mock_service.delete = AsyncMock(side_effect=ValueError("Task with id 999 not found"))

        with pytest.raises(HTTPException) as exc_info:
            await delete_task(task_id=999, service=mock_service)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_status_handler_not_found(self, mock_service):
        from src.api.handlers.task import update_task_status

        mock_service.update_status = AsyncMock(
            side_effect=ValueError("Task with id 999 not found")
        )

        with pytest.raises(HTTPException) as exc_info:
            await update_task_status(
                task_id=999,
                data=TaskStatusUpdate(status=TaskStatus.IN_PROGRESS),
                service=mock_service,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_update_status_handler_invalid_transition(self, mock_service):
        from src.api.handlers.task import update_task_status

        mock_service.update_status = AsyncMock(
            side_effect=ValueError("Invalid status transition from DONE to PENDING")
        )

        with pytest.raises(HTTPException) as exc_info:
            await update_task_status(
                task_id=1,
                data=TaskStatusUpdate(status=TaskStatus.PENDING),
                service=mock_service,
            )
        assert exc_info.value.status_code == 422

    @pytest.mark.asyncio
    async def test_list_tasks_handler(self, mock_service):
        from datetime import datetime, timezone
        from src.api.handlers.task import list_tasks

        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.title = "Test"
        mock_task.description = None
        mock_task.status = "PENDING"
        mock_task.priority = "MEDIUM"
        mock_task.estimated_hours = None
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.updated_at = datetime.now(timezone.utc)

        mock_service.list_tasks = AsyncMock(return_value=([mock_task], 1))
        mock_service._get_role_ids_for_task = AsyncMock(return_value=[])

        result = await list_tasks(
            page=1, page_size=20, role_id=None, status=None, service=mock_service
        )
        assert result.total == 1
        assert len(result.items) == 1
class TestTaskHandlerHTTP:
    """Test task HTTP endpoints via FastAPI TestClient."""

    @pytest.fixture
    def client(self):
        from fastapi.testclient import TestClient
        from main import app
        return TestClient(app)

    def test_create_task(self, client):
        r = client.post("/tasks", json={"title": "Test task"})
        assert r.status_code == 201
        data = r.json()
        assert data["title"] == "Test task"
        assert data["status"] == "PENDING"
        assert data["priority"] == "MEDIUM"

    def test_create_task_full(self, client):
        r = client.post(
            "/tasks",
            json={
                "title": "Full task",
                "description": "A detailed description",
                "priority": "HIGH",
                "estimated_hours": 5.5,
            },
        )
        assert r.status_code == 201
        data = r.json()
        assert data["title"] == "Full task"
        assert data["priority"] == "HIGH"
        assert data["estimated_hours"] == 5.5

    def test_create_task_invalid_title(self, client):
        r = client.post("/tasks", json={"title": ""})
        assert r.status_code == 422

    def test_get_task_not_found(self, client):
        r = client.get("/tasks/99999")
        assert r.status_code == 404

    def test_get_task_success(self, client):
        # Create first
        cr = client.post("/tasks", json={"title": "Get me"})
        task_id = cr.json()["id"]
        # Then get
        r = client.get(f"/tasks/{task_id}")
        assert r.status_code == 200
        assert r.json()["title"] == "Get me"

    def test_list_tasks_empty(self, client):
        r = client.get("/tasks")
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data

    def test_update_task(self, client):
        cr = client.post("/tasks", json={"title": "Old title"})
        task_id = cr.json()["id"]
        r = client.put(f"/tasks/{task_id}", json={"title": "New title", "priority": "URGENT"})
        assert r.status_code == 200
        assert r.json()["title"] == "New title"
        assert r.json()["priority"] == "URGENT"

    def test_update_task_not_found(self, client):
        r = client.put("/tasks/99999", json={"title": "Whatever"})
        assert r.status_code == 404

    def test_delete_task(self, client):
        cr = client.post("/tasks", json={"title": "Delete me"})
        task_id = cr.json()["id"]
        r = client.delete(f"/tasks/{task_id}")
        assert r.status_code == 204
        # Confirm deleted
        r2 = client.get(f"/tasks/{task_id}")
        assert r2.status_code == 404

    def test_delete_task_not_found(self, client):
        r = client.delete("/tasks/99999")
        assert r.status_code == 404

    def test_status_transition_pending_to_in_progress(self, client):
        cr = client.post("/tasks", json={"title": "Status test"})
        task_id = cr.json()["id"]
        r = client.patch(f"/tasks/{task_id}/status", json={"status": "IN_PROGRESS"})
        assert r.status_code == 200
        assert r.json()["status"] == "IN_PROGRESS"

    def test_status_transition_invalid(self, client):
        cr = client.post("/tasks", json={"title": "Status test"})
        task_id = cr.json()["id"]
        # PENDING → DONE is invalid (must go through IN_PROGRESS)
        r = client.patch(f"/tasks/{task_id}/status", json={"status": "DONE"})
        assert r.status_code == 422

    def test_status_transition_not_found(self, client):
        r = client.patch("/tasks/99999/status", json={"status": "IN_PROGRESS"})
        assert r.status_code == 404

    def test_filter_tasks_by_status(self, client):
        cr = client.post("/tasks", json={"title": "Filter test"})
        task_id = cr.json()["id"]
        # Must transition PENDING → IN_PROGRESS → DONE
        client.patch(f"/tasks/{task_id}/status", json={"status": "IN_PROGRESS"})
        client.patch(f"/tasks/{task_id}/status", json={"status": "DONE"})
        r = client.get("/tasks?status=DONE")
        assert r.status_code == 200
        items = r.json()["items"]
        done_ids = [item["id"] for item in items]
        assert task_id in done_ids

    def test_filter_tasks_by_role_id(self, client):
        # Create role first
        rc = client.post("/roles", json={"name": "Dev"})
        role_id = rc.json()["id"]
        # Create task with role
        cr = client.post("/tasks", json={"title": "Role filtered", "role_ids": [role_id]})
        task_id = cr.json()["id"]
        r = client.get(f"/tasks?role_id={role_id}")
        assert r.status_code == 200
        items = r.json()["items"]
        assert any(item["id"] == task_id for item in items)

    def test_create_task_with_invalid_role(self, client):
        """POST /tasks with role_ids referencing non-existent role returns 409."""
        r = client.post("/tasks", json={"title": "Bad roles", "role_ids": [99999]})
        assert r.status_code == 409

    def test_update_nonexistent_task(self, client):
        r = client.put("/tasks/99999", json={"title": "Whatever"})
        assert r.status_code == 404

    def test_list_tasks_pagination(self, client):
        r = client.get("/tasks?page=1&page_size=5")
        assert r.status_code == 200
        data = r.json()
        assert data["page"] == 1
        assert data["page_size"] == 5


# ─────────────────────────────────────────────────────────────────────────────
# Extended service tests — improving coverage on task modules
# ─────────────────────────────────────────────────────────────────────────────
class TestTaskServiceHelpers:
    """Test TaskService internal helpers."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_validate_role_ids_all_valid(self, mock_session):
        from src.services.task import TaskService

        # Roles 1 and 2 exist
        mock_result = MagicMock()
        mock_result.all.return_value = [(1,), (2,)]
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = TaskService(mock_session)
        # Should not raise
        await service._validate_role_ids([1, 2])

    @pytest.mark.asyncio
    async def test_validate_role_ids_some_missing(self, mock_session):
        from src.services.task import TaskService

        # Only role 1 exists
        mock_result = MagicMock()
        mock_result.all.return_value = [(1,)]
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = TaskService(mock_session)
        with pytest.raises(ValueError, match="not found"):
            await service._validate_role_ids([1, 999])

    @pytest.mark.asyncio
    async def test_validate_role_ids_empty_list(self, mock_session):
        from src.services.task import TaskService

        service = TaskService(mock_session)
        # Empty list is valid
        await service._validate_role_ids([])

    @pytest.mark.asyncio
    async def test_set_role_ids_replaces_existing(self, mock_session):
        from src.services.task import TaskService

        # Mock delete for existing
        mock_del_result = MagicMock()
        mock_session.execute = AsyncMock(return_value=mock_del_result)
        mock_session.commit = AsyncMock()

        service = TaskService(mock_session)
        await service._set_role_ids(1, [3, 4])
        # Should have added 2 RoleTask entries
        assert mock_session.add.call_count == 2
class TestTaskServiceExtended:
    """Extended TaskService tests for better coverage."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_create_task_with_roles_success(self, mock_session):
        from src.services.task import TaskService

        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.title = "Task with roles"

        # Mock role validation — roles exist
        mock_role_result = MagicMock()
        mock_role_result.all.return_value = [(1,), (2,)]
        mock_session.execute = AsyncMock(return_value=mock_role_result)

        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with patch("src.services.task.Task") as MockTask:
            MockTask.return_value = mock_task
            service = TaskService(mock_session)
            result = await service.create(
                TaskCreate(title="Task with roles", role_ids=[1, 2])
            )
        assert result.title == "Task with roles"
        # RoleTask adds: 2 (for role assignment)
        assert mock_session.add.call_count == 3  # 1 task + 2 role assignments

    @pytest.mark.asyncio
    async def test_create_task_integrity_error(self, mock_session):
        from sqlalchemy.exc import IntegrityError
        from src.services.task import TaskService

        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(side_effect=IntegrityError(None, None, None))
        mock_session.rollback = AsyncMock()

        with patch("src.services.task.Task") as MockTask:
            MockTask.return_value = MagicMock()
            service = TaskService(mock_session)
            with pytest.raises(ValueError, match="constraint"):
                await service.create(TaskCreate(title="Test"))

    @pytest.mark.asyncio
    async def test_update_task_success(self, mock_session):
        from src.services.task import TaskService

        mock_task = MagicMock()
        mock_task.title = "Original"
        mock_task.status = "PENDING"
        mock_task.priority = "MEDIUM"
        mock_task.estimated_hours = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        service = TaskService(mock_session)
        result = await service.update(
            1, TaskUpdate(title="Updated", priority=TaskPriority.HIGH)
        )
        assert mock_task.title == "Updated"
        assert mock_task.priority == "HIGH"

    @pytest.mark.asyncio
    async def test_update_task_with_role_ids(self, mock_session):
        from src.services.task import TaskService

        mock_task = MagicMock()
        mock_task.title = "Original"

        # Mock get_by_id
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task

        # Mock role validation
        mock_role_result = MagicMock()
        mock_role_result.all.return_value = [(1,)]

        # Mock _set_role_ids delete + add calls
        mock_del_result = MagicMock()

        mock_session.execute = AsyncMock(
            side_effect=[
                mock_result,        # get_by_id
                mock_role_result,   # _validate_role_ids
                mock_del_result,    # _set_role_ids delete
            ]
        )
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        service = TaskService(mock_session)
        result = await service.update(1, TaskUpdate(role_ids=[1]))
        assert mock_task.title == "Original"

    @pytest.mark.asyncio
    async def test_update_task_integrity_error(self, mock_session):
        from sqlalchemy.exc import IntegrityError
        from src.services.task import TaskService

        mock_task = MagicMock()
        mock_task.title = "Original"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock(side_effect=IntegrityError(None, None, None))
        mock_session.rollback = AsyncMock()

        service = TaskService(mock_session)
        with pytest.raises(ValueError, match="constraint"):
            await service.update(1, TaskUpdate(title="Updated"))

    @pytest.mark.asyncio
    async def test_delete_hard(self, mock_session):
        from src.services.task import TaskService

        mock_task = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()

        service = TaskService(mock_session)
        result = await service.delete(1, hard=True)
        assert result is True
        mock_session.delete.assert_called_once_with(mock_task)

    @pytest.mark.asyncio
    async def test_update_status_pending_to_cancelled(self, mock_session):
        from src.services.task import TaskService

        mock_task = MagicMock()
        mock_task.status = "PENDING"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        service = TaskService(mock_session)
        await service.update_status(1, TaskStatusUpdate(status=TaskStatus.CANCELLED))
        assert mock_task.status == "CANCELLED"

    @pytest.mark.asyncio
    async def test_update_status_in_progress_to_done(self, mock_session):
        from src.services.task import TaskService

        mock_task = MagicMock()
        mock_task.status = "IN_PROGRESS"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute = AsyncMock(return_value=mock_result)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        service = TaskService(mock_session)
        await service.update_status(1, TaskStatusUpdate(status=TaskStatus.DONE))
        assert mock_task.status == "DONE"

    @pytest.mark.asyncio
    async def test_update_status_invalid_pending_to_done(self, mock_session):
        """PENDING cannot go directly to DONE."""
        from src.services.task import TaskService

        mock_task = MagicMock()
        mock_task.status = "PENDING"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = TaskService(mock_session)
        with pytest.raises(ValueError, match="Invalid status transition"):
            await service.update_status(1, TaskStatusUpdate(status=TaskStatus.DONE))

    @pytest.mark.asyncio
    async def test_update_status_cancelled_is_terminal(self, mock_session):
        """CANCELLED cannot transition to anything."""
        from src.services.task import TaskService

        mock_task = MagicMock()
        mock_task.status = "CANCELLED"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_task
        mock_session.execute = AsyncMock(return_value=mock_result)

        service = TaskService(mock_session)
        with pytest.raises(ValueError, match="Invalid status transition"):
            await service.update_status(
                1, TaskStatusUpdate(status=TaskStatus.IN_PROGRESS)
            )

    @pytest.mark.asyncio
    async def test_list_tasks_with_role_id_filter(self, mock_session):
        from src.services.task import TaskService

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 1

        mock_task_result = MagicMock()
        mock_task_result.scalars.return_value.all.return_value = [MagicMock(id=5)]

        mock_session.execute = AsyncMock(
            side_effect=[mock_count_result, mock_task_result]
        )

        service = TaskService(mock_session)
        items, total = await service.list_tasks(role_id=3)
        assert total == 1
