"""WeChat Message SQLAlchemy model."""
from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from src.models import Base


class WeChatMessage(Base):
    """WeChat message entity — independent log table, no FK to Task/Role.

    Fields:
        from_user: OpenID of the sender (FromUserName)
        to_user: OpenID of the recipient (ToUserName)
        msg_type: Message type (text, image, event, etc.)
        content: Message content (for text messages)
        msg_id: Unique WeChat message ID (used for dedup)
        create_time: Unix timestamp when WeChat created the message
        raw_xml: Original XML payload for audit/debug
    """

    __tablename__ = "wechat_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    from_user: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    to_user: Mapped[str] = mapped_column(String(100), nullable=False)
    msg_type: Mapped[str] = mapped_column(String(50), nullable=False, default="text")
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    msg_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    raw_xml: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
