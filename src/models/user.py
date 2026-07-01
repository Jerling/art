"""User model for JWT auth login.

Sprint 4 收尾 — provides a minimal users table so we can issue
JWT tokens for the local beta.  The auth flow only needs:

- ``username`` — login identifier (unique)
- ``password_hash`` — bcrypt hash, never stored in plaintext
- ``is_admin`` — coarse-grained role flag for future RBAC

There is intentionally no email, profile, soft-delete, or
audit-log columns — the goal is to close the Sprint 4 functional
gap (no login endpoint), not to build a full user-management system.
Add those in a follow-up sprint if the product requires them.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class User(Base):
    """Auth user — single table for Sprint 4 local beta."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now(), onupdate=func.now()
    )
