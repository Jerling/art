"""WeChat Push Log SQLAlchemy model."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class WeChatPushLog(Base):
    """Record of a WeChat push notification attempt.

    Used for auditing, debugging, and monitoring push delivery.
    Each row represents one push attempt (including retries).

    Fields:
        push_type: Type of notification (TASK_CREATED, TASK_ASSIGNED, TASK_COMPLETED)
        openid: Recipient's WeChat OpenID
        task_id: Associated task ID (if applicable)
        success: Whether the push was delivered successfully
        error: Error message if failed
        msg_id: WeChat message ID if successful
        latency_ms: Round-trip time in milliseconds
        retries: Number of retry attempts (0 = first try succeeded)
    """

    __tablename__ = "wechat_push_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    push_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    openid: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    msg_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    latency_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
