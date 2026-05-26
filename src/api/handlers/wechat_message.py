"""WeChat Message API — GET /messages."""
import math
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict

from src.storage.database import get_session
from src.storage.wechat_message import WeChatMessageStore

router = APIRouter(prefix="/messages", tags=["messages"])


# ─── Schemas ───────────────────────────────────────────────────────────────────


class WeChatMessageResponse(BaseModel):
    """Schema for a WeChat message in API responses."""

    id: int
    from_user: str
    to_user: str
    msg_type: str
    content: str | None
    msg_id: str | None
    create_time: float  # Unix timestamp for WeChat compatibility
    raw_xml: str | None

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_model(cls, msg) -> "WeChatMessageResponse":
        return cls(
            id=msg.id,
            from_user=msg.from_user,
            to_user=msg.to_user,
            msg_type=msg.msg_type,
            content=msg.content,
            msg_id=msg.msg_id,
            create_time=msg.create_time.timestamp(),
            raw_xml=msg.raw_xml,
        )


class PaginatedMessagesResponse(BaseModel):
    """Paginated list of WeChat messages."""

    items: list[WeChatMessageResponse]
    total: int
    page: int
    page_size: int
    pages: int


# ─── Dependencies ──────────────────────────────────────────────────────────────


async def get_message_store(session=Depends(get_session)) -> WeChatMessageStore:
    """Dependency: WeChatMessageStore with a shared session."""
    return WeChatMessageStore(session)


# ─── Endpoints ─────────────────────────────────────────────────────────────────


@router.get(
    "",
    response_model=PaginatedMessagesResponse,
    summary="Query WeChat message history by openid",
    description=(
        "Returns paginated message history for a given FromUserName (openid). "
        "Messages are ordered by create_time descending (newest first)."
    ),
)
async def list_messages(
    openid: Annotated[str, Query(description="FromUserName / openid of the WeChat user")],
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    store: WeChatMessageStore = Depends(get_message_store),
) -> PaginatedMessagesResponse:
    """GET /messages?openid=xxx&page=1&page_size=20 — paginated message history."""
    items, total = await store.list_by_from_user(
        from_user=openid,
        page=page,
        page_size=page_size,
    )
    pages = math.ceil(total / page_size) if total > 0 else 0
    return PaginatedMessagesResponse(
        items=[WeChatMessageResponse.from_model(m) for m in items],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )
