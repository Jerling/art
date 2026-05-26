"""Storage layer for WeChat message persistence."""
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.wechat_message import WeChatMessage


class WeChatMessageStore:
    """Async CRUD store for WeChatMessage.

    All public methods validate preconditions before touching the DB.
    The webhook handler is responsible for signature/decryption validation
    before calling these methods.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def save(
        self,
        *,
        from_user: str,
        to_user: str,
        msg_type: str,
        content: str | None,
        msg_id: str | None,
        create_time: datetime,
        raw_xml: str | None,
    ) -> WeChatMessage:
        """Insert a WeChat message, deduplicating by msg_id.

        Raises:
            ValueError: If required fields are missing or invalid.
        """
        if not from_user:
            raise ValueError("from_user is required")
        if not to_user:
            raise ValueError("to_user is required")
        if not msg_type:
            raise ValueError("msg_type is required")

        msg = WeChatMessage(
            from_user=from_user,
            to_user=to_user,
            msg_type=msg_type,
            content=content,
            msg_id=msg_id,
            create_time=create_time,
            raw_xml=raw_xml,
        )
        self.session.add(msg)

        try:
            await self.session.commit()
            await self.session.refresh(msg)
        except IntegrityError:
            await self.session.rollback()
            # msg_id collision — treat as already stored
            if msg_id:
                existing = await self.get_by_msg_id(msg_id)
                if existing:
                    return existing
            raise ValueError("Failed to store WeChat message due to constraint violation")

        return msg

    async def get_by_msg_id(self, msg_id: str) -> WeChatMessage | None:
        """Fetch a message by WeChat msg_id."""
        result = await self.session.execute(
            select(WeChatMessage).where(WeChatMessage.msg_id == msg_id)
        )
        return result.scalar_one_or_none()

    async def list_by_from_user(
        self,
        from_user: str,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[WeChatMessage], int]:
        """Paginated message history for a given user's openid (from_user).

        Returns (items, total).
        """
        base = select(WeChatMessage).where(WeChatMessage.from_user == from_user)

        count_result = await self.session.execute(
            select(func.count(WeChatMessage.id)).where(WeChatMessage.from_user == from_user)
        )
        total = count_result.scalar_one()

        offset = (page - 1) * page_size
        result = await self.session.execute(
            base.order_by(WeChatMessage.create_time.desc()).offset(offset).limit(page_size)
        )
        return list(result.scalars().all()), total
