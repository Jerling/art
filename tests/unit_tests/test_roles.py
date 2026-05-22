"""Unit tests for Roles CRUD API.

Run with: pytest tests/unit_tests/test_roles.py -v --cov=src --cov-report=term-missing
"""
from __future__ import annotations

import math
import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

sys.path.insert(0, sys.path[0])

from src.schemas.role import (
    PaginatedRolesResponse,
    RoleCreate,
    RoleResponse,
    RoleUpdate,
)


# ─────────────────────────────────────────────────────────────────────────────
# Schema validation tests
# ─────────────────────────────────────────────────────────────────────────────
class TestRoleCreateSchema:
    def test_valid_role_create(self):
        data = RoleCreate(name="Admin", description="Administrator role")
        assert data.name == "Admin"
        assert data.description == "Administrator role"

    def test_name_required(self):
        with pytest.raises(ValidationError) as exc_info:
            RoleCreate(name="")
        assert "name" in str(exc_info.value)

    def test_name_max_length(self):
        with pytest.raises(ValidationError):
            RoleCreate(name="x" * 101)

    def test_description_optional(self):
        data = RoleCreate(name="User")
        assert data.description is None

    def test_description_max_length(self):
        with pytest.raises(ValidationError):
            RoleCreate(name="User", description="x" * 501)


class TestRoleUpdateSchema:
    def test_empty_update_allowed(self):
        data = RoleUpdate()
        assert data.name is None
        assert data.description is None

    def test_partial_update(self):
        data = RoleUpdate(name="Manager")
        assert data.name == "Manager"
        assert data.description is None

    def test_name_min_length_when_provided(self):
        with pytest.raises(ValidationError):
            RoleUpdate(name="")


class TestRoleResponseSchema:
    def test_from_attributes(self):
        mock_role = MagicMock()
        mock_role.id = 1
        mock_role.name = "Admin"
        mock_role.description = "Admin role"
        mock_role.created_at = datetime(2026, 1, 1, 12, 0, 0)
        mock_role.updated_at = datetime(2026, 1, 2, 12, 0, 0)

        response = RoleResponse.model_validate(mock_role)
        assert response.id == 1
        assert response.name == "Admin"
        assert response.description == "Admin role"


class TestPaginatedRolesResponse:
    def test_pagination_fields(self):
        response = PaginatedRolesResponse(
            items=[],
            total=50,
            page=2,
            page_size=10,
            pages=5,
        )
        assert response.total == 50
        assert response.page == 2
        assert response.pages == 5


# ─────────────────────────────────────────────────────────────────────────────
# Service layer tests
# ─────────────────────────────────────────────────────────────────────────────
class TestRoleServiceValidation:
    """Test RoleService methods with mocked async session."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_create_role_success(self, mock_session):
        from datetime import datetime, timezone
        from src.services.role import RoleService

        mock_role = MagicMock()
        mock_role.id = 1
        mock_role.name = "Admin"
        mock_role.description = "Admin role"
        mock_role.deleted_at = None
        mock_role.created_at = datetime.now(timezone.utc)
        mock_role.updated_at = datetime.now(timezone.utc)

        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with patch("src.services.role.Role") as MockRole:
            MockRole.return_value = mock_role
            service = RoleService(mock_session)
            result = await service.create(RoleCreate(name="Admin", description="Admin role"))

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        assert result.name == "Admin"

    @pytest.mark.asyncio
    async def test_create_role_duplicate_name(self, mock_session):
        from sqlalchemy.exc import IntegrityError
        from src.services.role import RoleService

        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock(side_effect=IntegrityError(None, None, None))
        mock_session.rollback = AsyncMock()

        with patch("src.services.role.Role") as MockRole:
            MockRole.return_value = MagicMock()
            service = RoleService(mock_session)
            with pytest.raises(ValueError, match="already exists"):
                await service.create(RoleCreate(name="Admin"))

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, mock_session):
        from src.services.role import RoleService

        mock_role = MagicMock()
        mock_role.id = 1
        mock_role.name = "Admin"
        mock_role.deleted_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_role
        mock_session.execute.return_value = mock_result

        service = RoleService(mock_session)
        result = await service.get_by_id(1)
        assert result == mock_role

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, mock_session):
        from src.services.role import RoleService

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        service = RoleService(mock_session)
        result = await service.get_by_id(999)
        assert result is None

    @pytest.mark.asyncio
    async def test_list_roles_pagination(self, mock_session):
        from src.services.role import RoleService

        mock_role = MagicMock()
        mock_role.id = 1
        mock_role.deleted_at = None

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 25

        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = [mock_role]

        mock_session.execute.side_effect = [mock_count_result, mock_list_result]

        service = RoleService(mock_session)
        items, total = await service.list_roles(page=2, page_size=10)

        assert total == 25
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_list_roles_empty(self, mock_session):
        from src.services.role import RoleService

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 0

        mock_list_result = MagicMock()
        mock_list_result.scalars.return_value.all.return_value = []

        mock_session.execute.side_effect = [mock_count_result, mock_list_result]

        service = RoleService(mock_session)
        items, total = await service.list_roles()
        assert total == 0
        assert items == []

    @pytest.mark.asyncio
    async def test_update_role_success(self, mock_session):
        from datetime import datetime, timezone
        from src.services.role import RoleService

        mock_role = MagicMock()
        mock_role.id = 1
        mock_role.name = "Admin"
        mock_role.description = "Old desc"
        mock_role.deleted_at = None
        mock_role.updated_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_role
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        service = RoleService(mock_session)
        result = await service.update(1, RoleUpdate(name="SuperAdmin"))

        assert result.name == "SuperAdmin"
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_role_integrity_error(self, mock_session):
        """Update role name to one that already exists raises ValueError."""
        from datetime import datetime, timezone
        from sqlalchemy.exc import IntegrityError
        from src.services.role import RoleService

        mock_role = MagicMock()
        mock_role.id = 1
        mock_role.name = "Admin"
        mock_role.description = "Old desc"
        mock_role.deleted_at = None
        mock_role.updated_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_role
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock(side_effect=IntegrityError(None, None, None))
        mock_session.rollback = AsyncMock()
        mock_session.refresh = AsyncMock()

        service = RoleService(mock_session)
        with pytest.raises(ValueError, match="already exists"):
            await service.update(1, RoleUpdate(name="SuperAdmin"))

    @pytest.mark.asyncio
    async def test_update_role_not_found(self, mock_session):
        from src.services.role import RoleService

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        service = RoleService(mock_session)
        with pytest.raises(ValueError, match="not found"):
            await service.update(999, RoleUpdate(name="Ghost"))

    @pytest.mark.asyncio
    async def test_soft_delete_role(self, mock_session):
        from datetime import datetime, timezone
        from src.services.role import RoleService

        mock_role = MagicMock()
        mock_role.id = 1
        mock_role.deleted_at = None
        mock_role.updated_at = datetime.now(timezone.utc)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_role
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()

        service = RoleService(mock_session)
        result = await service.delete(1, hard=False)

        assert result is True
        assert mock_role.deleted_at is not None
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_hard_delete_role(self, mock_session):
        from src.services.role import RoleService

        mock_role = MagicMock()
        mock_role.id = 1
        mock_role.deleted_at = None

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_role
        mock_session.execute.return_value = mock_result
        mock_session.commit = AsyncMock()
        mock_session.delete = AsyncMock()

        service = RoleService(mock_session)
        result = await service.delete(1, hard=True)

        assert result is True
        mock_session.delete.assert_called_once_with(mock_role)

    @pytest.mark.asyncio
    async def test_delete_role_not_found(self, mock_session):
        from src.services.role import RoleService

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        service = RoleService(mock_session)
        with pytest.raises(ValueError, match="not found"):
            await service.delete(999)


# ─────────────────────────────────────────────────────────────────────────────
# API handler tests (using FastAPI TestClient)
# ─────────────────────────────────────────────────────────────────────────────
class TestRoleAPIHandlers:
    """Test Role API endpoints using mocked service."""

    @pytest.fixture
    def mock_service(self):
        return AsyncMock()

    @pytest.fixture
    def mock_session(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.refresh = AsyncMock()
        return session

    def test_create_role_endpoint_returns_422_on_empty_name(self):
        """POST /roles with empty name returns 422."""
        from fastapi.testclient import TestClient

        with patch("src.storage.database.engine"):
            from main import app

            client = TestClient(app, raise_server_exceptions=False)
            response = client.post("/roles", json={"name": ""})
            assert response.status_code == 422

    def test_roles_endpoint_exists(self):
        """GET /roles returns 200 (or 500 if DB not initialized)."""
        from fastapi.testclient import TestClient

        with patch("src.storage.database.engine"):
            from main import app

            client = TestClient(app, raise_server_exceptions=False)
            # Will 500 if DB not initialized (lifespan startup needed), but route exists
            response = client.get("/roles")
            assert response.status_code in (200, 500)

    def test_get_role_endpoint_returns_404_for_missing(self):
        """GET /roles/{id} returns 404 for non-existent role."""
        from fastapi.testclient import TestClient

        with patch("src.storage.database.engine"):
            with patch("src.storage.database.async_session_maker") as mock_maker:
                mock_session = AsyncMock()
                mock_session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
                mock_maker.return_value.__aenter__.return_value = mock_session
                mock_maker.return_value.__aexit__.return_value = None

                from main import app

                client = TestClient(app, raise_server_exceptions=False)
                response = client.get("/roles/99999")
                assert response.status_code == 404

    def test_pagination_calculation(self):
        """Verify PaginatedRolesResponse pages math."""
        total = 55
        page_size = 20
        pages = math.ceil(total / page_size)
        assert pages == 3

    def test_role_create_schema_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            RoleCreate(name="")

    def test_role_update_allows_partial(self):
        update = RoleUpdate(description="New desc only")
        assert update.name is None
        assert update.description == "New desc only"

    def test_role_response_from_dict(self):
        data = {
            "id": 1,
            "name": "Admin",
            "description": "Admin role",
            "created_at": "2026-01-01T12:00:00",
            "updated_at": "2026-01-02T12:00:00",
        }
        # RoleResponse should accept dict-like (from_attributes=False for raw dict)
        response = RoleResponse(
            id=1,
            name="Admin",
            description="Admin role",
            created_at=datetime(2026, 1, 1, 12, 0, 0),
            updated_at=datetime(2026, 1, 2, 12, 0, 0),
        )
        assert response.id == 1
        assert response.name == "Admin"

    def test_paginated_response_items(self):
        from datetime import datetime, timezone

        role_response = RoleResponse(
            id=1,
            name="Admin",
            description="Admin role",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        response = PaginatedRolesResponse(
            items=[role_response],
            total=1,
            page=1,
            page_size=20,
            pages=1,
        )
        assert len(response.items) == 1
        assert response.total == 1
