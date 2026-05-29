"""SQLAlchemy models."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base for all SQLAlchemy models."""

    pass


from src.models.role import Role  # noqa: E402, F401
from src.models.role_task import RoleTask  # noqa: E402, F401
from src.models.task import Task  # noqa: E402, F401
from src.models.wechat_message import WeChatMessage  # noqa: E402, F401
from src.models.wechat_push_log import WeChatPushLog  # noqa: E402, F401
