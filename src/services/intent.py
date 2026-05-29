"""Intent processing service — orchestrates the full flow from parsed intent to task creation.

This service connects the IntentParser (AI layer) to the TaskService (domain layer)
and handles the decision logic:

  - CREATE_TASK → TaskService.create() → WeChat push notification
  - QUERY_TASK  → (future: list tasks, reply via WeChat)
  - UNKNOWN     → reply "无法理解，请换一种说法"
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.domain.intent import IntentAction, IntentData
from src.llm.base import LLMError
from src.llm.glm import analyze_intent
from src.schemas.task import TaskCreate, TaskPriority
from src.services.task import TaskService

if TYPE_CHECKING:
    from src.llm.glm import GLMProvider

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Result type
# ─────────────────────────────────────────────────────────────────────────────

class IntentResult:
    """Result of processing a WeChat message through the intent pipeline."""

    def __init__(
        self,
        intent: IntentData,
        task_created: bool = False,
        task_id: int | None = None,
        task_title: str | None = None,
        task_priority: str | None = None,
        task_estimated_hours: float | None = None,
        reply_text: str | None = None,
    ):
        self.intent = intent
        self.task_created = task_created
        self.task_id = task_id
        self.task_title = task_title
        self.task_priority = task_priority
        self.task_estimated_hours = task_estimated_hours
        self.reply_text = reply_text

    @property
    def action(self) -> IntentAction:
        return self.intent.action


# ─────────────────────────────────────────────────────────────────────────────
# Intent-to-Priority mapping (Intent uses lowercase, Task uses UPPERCASE)
# ─────────────────────────────────────────────────────────────────────────────

_INTENT_TO_TASK_PRIORITY: dict[str, TaskPriority] = {
    "low": TaskPriority.LOW,
    "medium": TaskPriority.MEDIUM,
    "high": TaskPriority.HIGH,
    "urgent": TaskPriority.URGENT,
}


# ─────────────────────────────────────────────────────────────────────────────
# Intent Service
# ─────────────────────────────────────────────────────────────────────────────

class IntentService:
    """Orchestrates the intent processing pipeline.

    Given a user message, this service:
      1. Calls the LLM-based IntentParser to extract structured intent
      2. Based on the intent action:
         - CREATE_TASK → creates a task via TaskService
         - UNKNOWN     → returns a fallback reply text
      3. Returns an IntentResult with task details and reply text

    Usage:
        service = IntentService(task_service)
        result = await service.process_message("下周三前完成 API 设计", openid="oABC123")
    """

    def __init__(self, task_service: TaskService) -> None:
        self._task_service = task_service

    async def process_message(
        self,
        message: str,
        openid: str,
        *,
        provider: GLMProvider | None = None,
    ) -> IntentResult:
        """Process a user message through the full intent pipeline.

        Args:
            message: The raw user message text from WeChat.
            openid: The sender's OpenID (used for reply routing).
            provider: Optional GLMProvider for dependency injection in tests.

        Returns:
            IntentResult with task creation status and reply text.
        """
        # Step 1: Parse intent via LLM
        intent = await self._safe_parse_intent(message, provider=provider)

        # Step 2: Dispatch based on action
        if intent.action == IntentAction.CREATE_TASK:
            return await self._handle_create_task(intent, openid)
        elif intent.action == IntentAction.QUERY_TASK:
            return await self._handle_query_task(intent, openid)
        else:
            return self._handle_unknown(intent, openid)

    async def _safe_parse_intent(
        self, message: str, *, provider: GLMProvider | None = None
    ) -> IntentData:
        """Parse intent with exception isolation.

        All LLM/network errors are caught and logged; returns UNKNOWN intent
        on failure so the pipeline can still send a graceful reply.
        """
        try:
            return await analyze_intent(message, provider=provider)
        except LLMError as exc:
            logger.error("[intent_service] LLM error parsing intent: %s", exc)
            return IntentData(
                action=IntentAction.UNKNOWN,
                confidence=0.0,
                raw_text=message,
            )
        except Exception as exc:
            logger.error(
                "[intent_service] Unexpected error parsing intent: %s", exc
            )
            return IntentData(
                action=IntentAction.UNKNOWN,
                confidence=0.0,
                raw_text=message,
            )

    async def _handle_create_task(
        self, intent: IntentData, openid: str
    ) -> IntentResult:
        """Create a task from a CREATE_TASK intent and build the reply."""
        task_data = self._build_task_create(intent, openid=openid)

        try:
            task = await self._task_service.create(task_data)
        except ValueError as exc:
            logger.error("[intent_service] Task creation failed: %s", exc)
            return IntentResult(
                intent=intent,
                task_created=False,
                reply_text="任务创建失败，请稍后重试。",
            )

        logger.info(
            "[intent_service] Task created: id=%d title=%r openid=%s",
            task.id,
            task.title,
            openid,
        )

        # Build confirmation reply
        reply = self._build_create_reply(task)

        return IntentResult(
            intent=intent,
            task_created=True,
            task_id=task.id,
            task_title=task.title,
            task_priority=task.priority,
            task_estimated_hours=task.estimated_hours,
            reply_text=reply,
        )

    async def _handle_query_task(
        self, intent: IntentData, openid: str
    ) -> IntentResult:
        """Handle QUERY_TASK intent (placeholder — lists task count)."""
        # TODO(t_506acd8a): implement task listing via TaskService.list_tasks()
        reply = "任务查询功能即将上线，请稍后再试。"
        return IntentResult(intent=intent, reply_text=reply)

    def _handle_unknown(
        self, intent: IntentData, openid: str
    ) -> IntentResult:
        """Handle UNKNOWN intent with a helpful fallback message."""
        reply = "无法理解，请换一种说法。例如：'明天完成 API 设计' 或 '下周三前提交报告'。"
        return IntentResult(intent=intent, reply_text=reply)

    def _build_task_create(self, intent: IntentData, openid: str | None = None) -> TaskCreate:
        """Convert an IntentData to a TaskCreate schema."""
        priority = None
        if intent.suggested_priority:
            priority = _INTENT_TO_TASK_PRIORITY.get(
                intent.suggested_priority.value, TaskPriority.MEDIUM
            )

        return TaskCreate(
            title=intent.title or (intent.raw_text[:100] if intent.raw_text else "未命名任务"),
            description=intent.raw_text,
            priority=priority or TaskPriority.MEDIUM,
            estimated_hours=intent.estimated_hours,
            openid=openid,
        )

    @staticmethod
    def _build_create_reply(task) -> str:
        """Build the WeChat push confirmation message."""
        hours_str = f"{task.estimated_hours}h" if task.estimated_hours else "未估算"
        return (
            f"✅ 任务已创建："
            f"「{task.title}」"
            f"\n优先级 {task.priority}"
            f"，预计 {hours_str}"
        )
