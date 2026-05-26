"""Services layer for Art agent.

Provides business logic services including:
- Role management
- Task management
- Role-Task associations
- WeChat message handling with MCP tool integration
- Intent processing (webhook → intent → task creation)
- WeChat push notifications
"""
from src.services.intent import IntentResult, IntentService
from src.services.role import RoleService
from src.services.role_task import RoleTaskService
from src.services.task import TaskService
from src.services.wechat_message import (
    ToolExecutionResult,
    WeChatMessageContext,
    WeChatMessageService,
)
from src.services.wechat_push import PushResult, WeChatPushService

__all__ = [
    "IntentResult",
    "IntentService",
    "PushResult",
    "RoleService",
    "RoleTaskService",
    "TaskService",
    "WeChatMessageContext",
    "WeChatMessageService",
    "ToolExecutionResult",
    "WeChatPushService",
]
