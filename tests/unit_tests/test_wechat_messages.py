"""Unit tests for WeChat message persistence.

Run with:
  pytest tests/unit_tests/test_wechat_messages.py -v --cov=src --cov-report=term-missing
"""
from __future__ import annotations

import sys
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, sys.path[0])

from src.models.wechat_message import WeChatMessage
from src.storage.wechat_message import WeChatMessageStore


# ─────────────────────────────────────────────────────────────────────────────
# Store unit tests (mocked session)
# ─────────────────────────────────────────────────────────────────────────────


class TestWeChatMessageStore:
    """Tests for WeChatMessageStore with mocked AsyncSession."""

    def _make_mock_session(self):
        session = AsyncMock()
        session.commit = AsyncMock()
        session.rollback = AsyncMock()
        session.refresh = AsyncMock()
        session.add = MagicMock()
        return session

    def _make_mock_result(self, scalar_one_or_none=None, scalars_all=None, scalar_one=None):
        result = MagicMock()
        result.scalar_one_or_none = MagicMock(return_value=scalar_one_or_none)
        result.scalars = MagicMock(return_value=MagicMock(all=MagicMock(return_value=scalars_all or [])))
        result.scalar_one = MagicMock(return_value=scalar_one or 0)
        return result

    @pytest.mark.asyncio
    async def test_save_valid_message(self):
        session = self._make_mock_session()
        store = WeChatMessageStore(session)

        msg = await store.save(
            from_user="oABC123",
            to_user="gh_xyz",
            msg_type="text",
            content="Hello world",
            msg_id="1234567890",
            create_time=datetime(2026, 5, 22, 10, 0, 0),
            raw_xml="<xml>...</xml>",
        )

        session.add.assert_called_once()
        session.commit.assert_called_once()
        session.refresh.assert_called_once()
        assert msg.from_user == "oABC123"
        assert msg.content == "Hello world"

    @pytest.mark.asyncio
    async def test_save_missing_from_user_raises(self):
        session = self._make_mock_session()
        store = WeChatMessageStore(session)

        with pytest.raises(ValueError, match="from_user is required"):
            await store.save(
                from_user="",
                to_user="gh_xyz",
                msg_type="text",
                content="Hello",
                msg_id=None,
                create_time=datetime.now(),
                raw_xml=None,
            )

    @pytest.mark.asyncio
    async def test_save_missing_to_user_raises(self):
        session = self._make_mock_session()
        store = WeChatMessageStore(session)

        with pytest.raises(ValueError, match="to_user is required"):
            await store.save(
                from_user="oABC123",
                to_user="",
                msg_type="text",
                content="Hello",
                msg_id=None,
                create_time=datetime.now(),
                raw_xml=None,
            )

    @pytest.mark.asyncio
    async def test_save_missing_msg_type_raises(self):
        session = self._make_mock_session()
        store = WeChatMessageStore(session)

        with pytest.raises(ValueError, match="msg_type is required"):
            await store.save(
                from_user="oABC123",
                to_user="gh_xyz",
                msg_type="",
                content="Hello",
                msg_id=None,
                create_time=datetime.now(),
                raw_xml=None,
            )

    @pytest.mark.asyncio
    async def test_get_by_msg_id_found(self):
        session = self._make_mock_session()
        mock_msg = MagicMock(spec=WeChatMessage)
        mock_msg.msg_id = "123456"
        mock_result = self._make_mock_result(scalar_one_or_none=mock_msg)
        session.execute = AsyncMock(return_value=mock_result)

        store = WeChatMessageStore(session)
        result = await store.get_by_msg_id("123456")
        assert result == mock_msg

    @pytest.mark.asyncio
    async def test_get_by_msg_id_not_found(self):
        session = self._make_mock_session()
        mock_result = self._make_mock_result(scalar_one_or_none=None)
        session.execute = AsyncMock(return_value=mock_result)

        store = WeChatMessageStore(session)
        result = await store.get_by_msg_id("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_list_by_from_user_paginated(self):
        session = self._make_mock_session()

        mock_msgs = [
            MagicMock(spec=WeChatMessage, from_user="oABC", id=1),
            MagicMock(spec=WeChatMessage, from_user="oABC", id=2),
        ]
        mock_result = self._make_mock_result(scalar_one=5, scalars_all=mock_msgs)
        session.execute = AsyncMock(return_value=mock_result)

        store = WeChatMessageStore(session)
        items, total = await store.list_by_from_user("oABC", page=1, page_size=2)

        assert items == mock_msgs
        assert total == 5
        # count query + items query
        assert session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_list_by_from_user_page_2(self):
        session = self._make_mock_session()

        mock_result = self._make_mock_result(scalar_one=10, scalars_all=[])
        session.execute = AsyncMock(return_value=mock_result)

        store = WeChatMessageStore(session)
        items, total = await store.list_by_from_user("oABC", page=2, page_size=5)

        assert items == []
        assert total == 10
        # count query + items query
        assert session.execute.call_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# Model field tests
# ─────────────────────────────────────────────────────────────────────────────


class TestWeChatMessageModel:
    def test_tablename(self):
        assert WeChatMessage.__tablename__ == "wechat_messages"

    def test_fields_present(self):
        field_names = {c.name for c in WeChatMessage.__table__.columns}
        expected = {
            "id",
            "from_user",
            "to_user",
            "msg_type",
            "content",
            "msg_id",
            "create_time",
            "raw_xml",
            "created_at",
        }
        assert expected.issubset(field_names)

    def test_from_user_indexed(self):
        from_user_col = WeChatMessage.__table__.columns["from_user"]
        assert from_user_col.index

    def test_msg_id_indexed(self):
        msg_id_col = WeChatMessage.__table__.columns["msg_id"]
        assert msg_id_col.index
