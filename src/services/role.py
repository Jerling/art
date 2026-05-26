"""Service layer for Role CRUD operations."""
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.role import Role
from src.schemas.role import RoleCreate, RoleUpdate

UTC = UTC


class RoleService:
    """CRUD operations for Role."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, data: RoleCreate) -> Role:
        """Create a new role."""
        role = Role(name=data.name, description=data.description)
        self.session.add(role)
        try:
            await self.session.commit()
            await self.session.refresh(role)
        except IntegrityError:
            await self.session.rollback()
            raise ValueError(f"Role with name '{data.name}' already exists")
        return role

    async def get_by_id(self, role_id: int) -> Role | None:
        """Get a role by ID (excludes soft-deleted)."""
        result = await self.session.execute(
            select(Role).where(Role.id == role_id, Role.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_roles(self, page: int = 1, page_size: int = 20) -> tuple[list[Role], int]:
        """List roles with pagination (excludes soft-deleted)."""
        # Total count
        count_result = await self.session.execute(
            select(func.count(Role.id)).where(Role.deleted_at.is_(None))
        )
        total = count_result.scalar_one()

        # Paginated items
        offset = (page - 1) * page_size
        result = await self.session.execute(
            select(Role)
            .where(Role.deleted_at.is_(None))
            .order_by(Role.id)
            .offset(offset)
            .limit(page_size)
        )
        items = list(result.scalars().all())
        return items, total

    async def update(self, role_id: int, data: RoleUpdate) -> Role:
        """Update a role. Returns updated role or raises ValueError if not found."""
        role = await self.get_by_id(role_id)
        if not role:
            raise ValueError(f"Role with id {role_id} not found")

        if data.name is not None:
            role.name = data.name
        if data.description is not None:
            role.description = data.description
        role.updated_at = datetime.now(UTC)

        try:
            await self.session.commit()
            await self.session.refresh(role)
        except IntegrityError:
            await self.session.rollback()
            raise ValueError(f"Role with name '{data.name}' already exists")
        return role

    async def delete(self, role_id: int, hard: bool = False) -> bool:
        """Delete a role. Soft-delete by default, hard-delete if hard=True."""
        role = await self.get_by_id(role_id)
        if not role:
            raise ValueError(f"Role with id {role_id} not found")

        if hard:
            await self.session.delete(role)
        else:
            role.deleted_at = datetime.now(UTC)
        await self.session.commit()
        return True
