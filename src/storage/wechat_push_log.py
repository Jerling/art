"""WeChat Push Log database storage.

CRUD operations for WeChatPushLog records.
"""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.wechat_push_log import WeChatPushLog
from src.services.wechat_push import PushLog

logger = logging.getLogger(__name__)


class WeChatPushLogStore:
    """Database operations for WeChat push logs."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(self, log: PushLog) -> WeChatPushLog:
        """Save a push log record to the database."""
        record = WeChatPushLog(
            push_type=log.push_type,
            openid=log.openid,
            task_id=log.task_id,
            success=log.success,
            error=log.error,
            msg_id=log.msg_id,
            latency_ms=log.latency_ms,
            retries=log.retries,
            created_at=log.created_at,
        )
        self.session.add(record)
        await self.session.commit()
        await self.session.refresh(record)
        logger.debug(
            "[push_log] saved: type=%s openid=%s task_id=%s success=%s",
            log.push_type,
            log.openid,
            log.task_id,
            log.success,
        )
        return record

    async def list_logs(
        self,
        *,
        openid: str | None = None,
        task_id: int | None = None,
        push_type: str | None = None,
        success: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[WeChatPushLog], int]:
        """List push logs with optional filters, newest first."""
        base = select(WeChatPushLog)

        if openid is not None:
            base = base.where(WeChatPushLog.openid == openid)
        if task_id is not None:
            base = base.where(WeChatPushLog.task_id == task_id)
        if push_type is not None:
            base = base.where(WeChatPushLog.push_type == push_type)
        if success is not None:
            base = base.where(WeChatPushLog.success == success)

        # Total count
        count_query = select(func.count(WeChatPushLog.id))
        if openid is not None:
            count_query = count_query.where(WeChatPushLog.openid == openid)
        if task_id is not None:
            count_query = count_query.where(WeChatPushLog.task_id == task_id)
        if push_type is not None:
            count_query = count_query.where(WeChatPushLog.push_type == push_type)
        if success is not None:
            count_query = count_query.where(WeChatPushLog.success == success)

        count_result = await self.session.execute(count_query)
        total = count_result.scalar_one()

        # Paginated items, newest first
        result = await self.session.execute(
            base.order_by(desc(WeChatPushLog.id)).offset(offset).limit(limit)
        )
        items = list(result.scalars().all())
        return items, total

    async def get_by_id(self, log_id: int) -> WeChatPushLog | None:
        """Get a push log record by ID."""
        result = await self.session.execute(
            select(WeChatPushLog).where(WeChatPushLog.id == log_id)
        )
        return result.scalar_one_or_none()
