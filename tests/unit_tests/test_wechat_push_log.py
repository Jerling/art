"""Unit tests for WeChat Push Log store.

Run with:
  pytest tests/unit_tests/test_wechat_push_log.py -v --cov=src --cov-report=term-missing
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.wechat_push import PushLog, PushType
from src.storage.wechat_push_log import WeChatPushLogStore


class TestWeChatPushLogStore:
    """Tests for WeChatPushLogStore database operations."""

    @pytest.fixture
    def mock_session(self):
        return AsyncMock()

    @pytest.mark.asyncio
    async def test_save_push_log(self, mock_session):
        """Test: save() creates a WeChatPushLog record."""
        store = WeChatPushLogStore(mock_session)

        log = PushLog(
            push_type=PushType.TASK_CREATED.value,
            openid="oABC123",
            task_id=42,
            success=True,
            msg_id="msg_123",
            latency_ms=150.0,
            retries=0,
        )

        result = await store.save(log)

        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

        # Verify the record that was added
        added_record = mock_session.add.call_args[0][0]
        assert added_record.push_type == PushType.TASK_CREATED.value
        assert added_record.openid == "oABC123"
        assert added_record.task_id == 42
        assert added_record.success is True
        assert added_record.msg_id == "msg_123"
        assert added_record.latency_ms == 150.0

    @pytest.mark.asyncio
    async def test_save_failed_push_log(self, mock_session):
        """Test: save() records failed push correctly."""
        store = WeChatPushLogStore(mock_session)

        log = PushLog(
            push_type=PushType.TASK_ASSIGNED.value,
            openid="oXYZ",
            task_id=10,
            success=False,
            error="HTTP timeout",
            retries=3,
            latency_ms=10500.0,
        )

        await store.save(log)

        added_record = mock_session.add.call_args[0][0]
        assert added_record.success is False
        assert added_record.error == "HTTP timeout"
        assert added_record.retries == 3

    @pytest.mark.asyncio
    async def test_list_logs_basic(self, mock_session):
        """Test: list_logs() returns paginated results."""
        store = WeChatPushLogStore(mock_session)

        mock_logs = [
            MagicMock(id=3, push_type="TASK_CREATED"),
            MagicMock(id=2, push_type="TASK_ASSIGNED"),
            MagicMock(id=1, push_type="TASK_CREATED"),
        ]

        # Mock count result
        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 3

        # Mock list result
        mock_list_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = mock_logs
        mock_list_result.scalars.return_value.all.return_value = mock_logs

        mock_session.execute = AsyncMock(
            side_effect=[mock_count_result, mock_list_result]
        )

        items, total = await store.list_logs()

        assert total == 3
        assert len(items) == 3

    @pytest.mark.asyncio
    async def test_list_logs_with_openid_filter(self, mock_session):
        """Test: list_logs() filters by openid."""
        store = WeChatPushLogStore(mock_session)

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 1

        mock_list_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [MagicMock(id=1)]
        mock_list_result.scalars.return_value.all.return_value = [MagicMock(id=1)]

        mock_session.execute = AsyncMock(
            side_effect=[mock_count_result, mock_list_result]
        )

        items, total = await store.list_logs(openid="oABC123")

        assert total == 1
        assert len(items) == 1

    @pytest.mark.asyncio
    async def test_list_logs_with_task_id_filter(self, mock_session):
        """Test: list_logs() filters by task_id."""
        store = WeChatPushLogStore(mock_session)

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 2

        mock_list_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [MagicMock(), MagicMock()]
        mock_list_result.scalars.return_value.all.return_value = [MagicMock(), MagicMock()]

        mock_session.execute = AsyncMock(
            side_effect=[mock_count_result, mock_list_result]
        )

        items, total = await store.list_logs(task_id=42)

        assert total == 2

    @pytest.mark.asyncio
    async def test_list_logs_with_success_filter(self, mock_session):
        """Test: list_logs() filters by success status."""
        store = WeChatPushLogStore(mock_session)

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 5

        mock_list_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [MagicMock()] * 5
        mock_list_result.scalars.return_value.all.return_value = [MagicMock()] * 5

        mock_session.execute = AsyncMock(
            side_effect=[mock_count_result, mock_list_result]
        )

        items, total = await store.list_logs(success=True)

        assert total == 5

    @pytest.mark.asyncio
    async def test_list_logs_pagination(self, mock_session):
        """Test: list_logs() respects limit and offset."""
        store = WeChatPushLogStore(mock_session)

        mock_count_result = MagicMock()
        mock_count_result.scalar_one.return_value = 100

        mock_list_result = MagicMock()
        mock_scalars = MagicMock()
        mock_scalars.all.return_value = [MagicMock()] * 10
        mock_list_result.scalars.return_value.all.return_value = [MagicMock()] * 10

        mock_session.execute = AsyncMock(
            side_effect=[mock_count_result, mock_list_result]
        )

        items, total = await store.list_logs(limit=10, offset=20)

        assert total == 100
        assert len(items) == 10

    @pytest.mark.asyncio
    async def test_get_by_id_found(self, mock_session):
        """Test: get_by_id() returns a record when found."""
        store = WeChatPushLogStore(mock_session)

        expected_log = MagicMock(id=1, push_type="TASK_CREATED")
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_log
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await store.get_by_id(1)

        assert result == expected_log

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, mock_session):
        """Test: get_by_id() returns None when not found."""
        store = WeChatPushLogStore(mock_session)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await store.get_by_id(999)
        assert result is None
