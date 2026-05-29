"""Task SQLAlchemy model."""
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class Task(Base):
    """Task entity — full CRUD is in t_e7bce8be; this is the model only."""

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="PENDING"
    )
    priority: Mapped[str] = mapped_column(
        String(20), nullable=False, default="MEDIUM"
    )
    estimated_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    openid: Mapped[str | None] = mapped_column(String(128), nullable=True, default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
