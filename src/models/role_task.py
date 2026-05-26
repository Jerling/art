"""Role-Task many-to-many association model."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class RoleTask(Base):
    """Junction table for role-task many-to-many relationships."""

    __tablename__ = "role_tasks"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
