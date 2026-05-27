"""Unit tests for Sprint 3 WeChat push notification enhancements.

Tests:
  - Retry mechanism with exponential backoff
  - Rate limiter
  - Push log recording
  - Task assignment notification
  - Task completion notification
  - PushLog model

Run with:
  pytest tests/unit_tests/test_wechat_push_sprint3.py -v --cov=src --cov-report=term-missing
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.services.wechat_push import (
    PushLog,
    PushResult,
    PushType,
    RateLimiter,
    TokenCache,
    WeChatPushService,
)


# ─────────────────────────────────────────────────────────────────────────────
# TokenCache tests
# ─────────────────────────────────────────────────────────────────────────────

class TestTokenCache:
    def test_empty_cache_not_valid(self):
        cache = TokenCache()
        assert cache.is_valid is False

    def test_valid_cache(self):
        import time

        cache = TokenCache(token="abc", expires_at=time.time() + 7200)
        assert cache.is_valid is True

    def test_expired_cache_not_valid(self):
        import time

        cache = TokenCache(token="abc", expires_at=time.time() - 100)
        assert cache.is_valid is False

    def test_cache_within_buffer_not_valid(self):
        import time

        # expires in 2 minutes (less than 5-min buffer)
        cache = TokenCache(token="abc", expires_at=time.time() + 120)
        assert cache.is_valid is False


# ─────────────────────────────────────────────────────────────────────────────
# RateLimiter tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_first_request_passes_immediately(self):
        limiter = RateLimiter(max_tokens=10, refill_rate=10)
        start = asyncio.get_event_loop().time()
        await limiter.acquire()
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 0.1  # Should be nearly instant

    @pytest.mark.asyncio
    async def test_exhausted_tokens_causes_wait(self):
        limiter = RateLimiter(max_tokens=1, refill_rate=1)
        # First call uses the only token
        await limiter.acquire()
        # Second call should wait for refill
        import time

        start = time.monotonic()
        await limiter.acquire()
        elapsed = time.monotonic() - start
        assert elapsed >= 0.5  # Should wait ~1s for 1 token at 1/s

    @pytest.mark.asyncio
    async def test_refill_over_time(self):
        limiter = RateLimiter(max_tokens=2, refill_rate=100)
        # Exhaust tokens
        await limiter.acquire()
        await limiter.acquire()
        # Wait for refill
        await asyncio.sleep(0.1)
        # Should have ~10 tokens now
        start = asyncio.get_event_loop().time()
        await limiter.acquire()
        elapsed = asyncio.get_event_loop().time() - start
        assert elapsed < 0.05  # Should be fast after refill


# ─────────────────────────────────────────────────────────────────────────────
# PushLog tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPushLog:
    def test_push_log_defaults(self):
        log = PushLog(
            push_type=PushType.TASK_CREATED,
            openid="oABC123",
            task_id=1,
            success=True,
        )
        assert log.push_type == PushType.TASK_CREATED
        assert log.openid == "oABC123"
        assert log.task_id == 1
        assert log.success is True
        assert log.error is None
        assert log.msg_id is None
        assert log.latency_ms == 0.0
        assert log.retries == 0
        assert isinstance(log.created_at, datetime)

    def test_push_log_with_error(self):
        log = PushLog(
            push_type=PushType.TASK_ASSIGNED,
            openid="oXYZ",
            task_id=2,
            success=False,
            error="HTTP timeout",
            retries=3,
        )
        assert log.success is False
        assert log.error == "HTTP timeout"
        assert log.retries == 3


# ─────────────────────────────────────────────────────────────────────────────
# WeChatPushService - Retry mechanism tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWeChatPushRetry:
    """Tests for the retry mechanism with exponential backoff."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        """Test: success on first try, no retries needed."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test-token",
            "expires_in": 7200,
        }
        send_resp = MagicMock()
        send_resp.json.return_value = {"errcode": 0, "errmsg": "ok", "msgid": "msg_1"}

        mock_client.get.return_value = token_resp
        mock_client.post.return_value = send_resp

        service = WeChatPushService(
            app_id="test_app",
            app_secret="test_secret",
        )
        service._client = mock_client

        result = await service.send_text("oABC123", "test message")

        assert result.success is True
        assert result.retries == 0
        assert result.msg_id == "msg_1"

    @pytest.mark.asyncio
    async def test_retry_on_timeout_then_succeed(self):
        """Test: timeout on first attempt, success on retry."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test-token",
            "expires_in": 7200,
        }
        send_resp_success = MagicMock()
        send_resp_success.json.return_value = {"errcode": 0, "errmsg": "ok", "msgid": "msg_2"}

        mock_client.get.return_value = token_resp
        # First post times out, second succeeds
        mock_client.post.side_effect = [
            httpx.TimeoutException("timeout"),
            send_resp_success,
        ]

        service = WeChatPushService(
            app_id="test_app",
            app_secret="test_secret",
        )
        service._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await service.send_text("oABC123", "test message")

        assert result.success is True
        assert result.retries == 1  # Succeeded on 2nd attempt
        assert mock_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_on_error_code_then_succeed(self):
        """Test: error code on first attempt, success on retry."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test-token",
            "expires_in": 7200,
        }
        send_resp_fail = MagicMock()
        send_resp_fail.json.return_value = {"errcode": 43004, "errmsg": "require subscribe"}
        send_resp_success = MagicMock()
        send_resp_success.json.return_value = {"errcode": 0, "errmsg": "ok", "msgid": "msg_3"}

        mock_client.get.return_value = token_resp
        mock_client.post.side_effect = [send_resp_fail, send_resp_success]

        service = WeChatPushService(
            app_id="test_app",
            app_secret="test_secret",
        )
        service._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await service.send_text("oABC123", "test message")

        assert result.success is True
        assert result.retries == 1

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self):
        """Test: all 3 retries fail → final failure."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test-token",
            "expires_in": 7200,
        }
        send_resp_fail = MagicMock()
        send_resp_fail.json.return_value = {"errcode": 43004, "errmsg": "require subscribe"}

        mock_client.get.return_value = token_resp
        mock_client.post.return_value = send_resp_fail

        service = WeChatPushService(
            app_id="test_app",
            app_secret="test_secret",
        )
        service._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await service.send_text("oABC123", "test message")

        assert result.success is False
        assert result.retries == 2  # 0-indexed, 3 attempts = max retries 2
        assert "43004" in result.error
        assert mock_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_retry_exponential_backoff_delays(self):
        """Test: retry delays follow exponential backoff (1s, 2s)."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test-token",
            "expires_in": 7200,
        }
        send_resp_fail = MagicMock()
        send_resp_fail.json.return_value = {"errcode": 43004, "errmsg": "error"}
        send_resp_success = MagicMock()
        send_resp_success.json.return_value = {"errcode": 0, "errmsg": "ok"}

        mock_client.get.return_value = token_resp
        mock_client.post.side_effect = [
            send_resp_fail,
            send_resp_fail,
            send_resp_success,
        ]

        service = WeChatPushService(
            app_id="test_app",
            app_secret="test_secret",
        )
        service._client = mock_client

        sleep_calls = []

        async def mock_sleep(delay):
            sleep_calls.append(delay)

        with patch("asyncio.sleep", side_effect=mock_sleep):
            result = await service.send_text("oABC123", "test")

        assert result.success is True
        assert len(sleep_calls) == 2
        assert sleep_calls[0] == 1.0  # 2^0
        assert sleep_calls[1] == 2.0  # 2^1

    @pytest.mark.asyncio
    async def test_token_invalidation_triggers_retry(self):
        """Test: errcode 40001 invalidates token and retries."""
        from src.services.wechat_push import _token_cache

        # Reset token cache
        _token_cache.token = ""
        _token_cache.expires_at = 0.0

        mock_client = AsyncMock()
        mock_client.is_closed = False

        # First token response
        token_resp1 = MagicMock()
        token_resp1.json.return_value = {
            "access_token": "token-1",
            "expires_in": 7200,
        }
        # Second token response (after invalidation)
        token_resp2 = MagicMock()
        token_resp2.json.return_value = {
            "access_token": "token-2",
            "expires_in": 7200,
        }
        # First send fails with token error
        send_resp_fail = MagicMock()
        send_resp_fail.json.return_value = {"errcode": 40001, "errmsg": "invalid credential"}
        # Second send succeeds
        send_resp_success = MagicMock()
        send_resp_success.json.return_value = {"errcode": 0, "errmsg": "ok"}

        mock_client.get.side_effect = [token_resp1, token_resp2]
        mock_client.post.side_effect = [send_resp_fail, send_resp_success]

        service = WeChatPushService(
            app_id="test_app",
            app_secret="test_secret",
        )
        service._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = await service.send_text("oABC123", "test")

        assert result.success is True
        assert result.retries == 1
        # Token should have been refreshed
        assert mock_client.get.call_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# WeChatPushService - New notification methods
# ─────────────────────────────────────────────────────────────────────────────

class TestWeChatPushNewMethods:
    """Tests for send_task_assigned and send_task_completed."""

    @pytest.mark.asyncio
    async def test_send_task_assigned(self):
        """Test: send_task_assigned builds correct message."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test-token",
            "expires_in": 7200,
        }
        send_resp = MagicMock()
        send_resp.json.return_value = {"errcode": 0, "errmsg": "ok", "msgid": "msg_assign"}

        mock_client.get.return_value = token_resp
        mock_client.post.return_value = send_resp

        service = WeChatPushService(
            app_id="test_app",
            app_secret="test_secret",
        )
        service._client = mock_client

        result = await service.send_task_assigned(
            openid="oABC123",
            task_id=42,
            task_title="完成 API 设计",
            role_name="后端开发",
        )

        assert result.success is True
        assert result.msg_id == "msg_assign"
        # Verify the message content
        call_args = mock_client.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        text_content = payload["text"]["content"]
        assert "新任务分配" in text_content
        assert "完成 API 设计" in text_content
        assert "后端开发" in text_content

    @pytest.mark.asyncio
    async def test_send_task_completed(self):
        """Test: send_task_completed builds correct message."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test-token",
            "expires_in": 7200,
        }
        send_resp = MagicMock()
        send_resp.json.return_value = {"errcode": 0, "errmsg": "ok", "msgid": "msg_done"}

        mock_client.get.return_value = token_resp
        mock_client.post.return_value = send_resp

        service = WeChatPushService(
            app_id="test_app",
            app_secret="test_secret",
        )
        service._client = mock_client

        result = await service.send_task_completed(
            openid="oABC123",
            task_id=42,
            task_title="完成 API 设计",
        )

        assert result.success is True
        assert result.msg_id == "msg_done"
        # Verify the message content
        call_args = mock_client.post.call_args
        payload = call_args.kwargs.get("json") or call_args[1].get("json")
        text_content = payload["text"]["content"]
        assert "任务已完成" in text_content
        assert "完成 API 设计" in text_content

    @pytest.mark.asyncio
    async def test_send_task_assigned_with_push_log(self):
        """Test: send_task_assigned records push log via on_log callback."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test-token",
            "expires_in": 7200,
        }
        send_resp = MagicMock()
        send_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}

        mock_client.get.return_value = token_resp
        mock_client.post.return_value = send_resp

        log_records = []

        async def on_log(log):
            log_records.append(log)

        service = WeChatPushService(
            app_id="test_app",
            app_secret="test_secret",
            on_log=on_log,
        )
        service._client = mock_client

        await service.send_task_assigned(
            openid="oABC123",
            task_id=42,
            task_title="Test Task",
            role_name="Developer",
        )

        assert len(log_records) == 1
        assert log_records[0].push_type == PushType.TASK_ASSIGNED.value
        assert log_records[0].openid == "oABC123"
        assert log_records[0].task_id == 42
        assert log_records[0].success is True

    @pytest.mark.asyncio
    async def test_send_task_completed_with_push_log(self):
        """Test: send_task_completed records push log via on_log callback."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test-token",
            "expires_in": 7200,
        }
        send_resp = MagicMock()
        send_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}

        mock_client.get.return_value = token_resp
        mock_client.post.return_value = send_resp

        log_records = []

        async def on_log(log):
            log_records.append(log)

        service = WeChatPushService(
            app_id="test_app",
            app_secret="test_secret",
            on_log=on_log,
        )
        service._client = mock_client

        await service.send_task_completed(
            openid="oABC123",
            task_id=42,
            task_title="Test Task",
        )

        assert len(log_records) == 1
        assert log_records[0].push_type == PushType.TASK_COMPLETED.value
        assert log_records[0].success is True


# ─────────────────────────────────────────────────────────────────────────────
# WeChatPushService - Push log recording tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPushLogRecording:
    """Tests for push log recording via on_log callback."""

    @pytest.mark.asyncio
    async def test_on_log_called_on_success(self):
        """Test: on_log callback is invoked on successful push."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test-token",
            "expires_in": 7200,
        }
        send_resp = MagicMock()
        send_resp.json.return_value = {"errcode": 0, "errmsg": "ok", "msgid": "msg_1"}

        mock_client.get.return_value = token_resp
        mock_client.post.return_value = send_resp

        log_records = []

        async def on_log(log):
            log_records.append(log)

        service = WeChatPushService(
            app_id="test_app",
            app_secret="test_secret",
            on_log=on_log,
        )
        service._client = mock_client

        await service.send_text(
            "oABC123",
            "test",
            push_type=PushType.TASK_CREATED,
            task_id=1,
        )

        assert len(log_records) == 1
        assert log_records[0].push_type == PushType.TASK_CREATED.value
        assert log_records[0].openid == "oABC123"
        assert log_records[0].task_id == 1
        assert log_records[0].success is True
        assert log_records[0].msg_id == "msg_1"
        assert log_records[0].error is None

    @pytest.mark.asyncio
    async def test_on_log_called_on_failure(self):
        """Test: on_log callback is invoked on failed push."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test-token",
            "expires_in": 7200,
        }
        send_resp = MagicMock()
        send_resp.json.return_value = {"errcode": 43004, "errmsg": "require subscribe"}

        mock_client.get.return_value = token_resp
        mock_client.post.return_value = send_resp

        log_records = []

        async def on_log(log):
            log_records.append(log)

        service = WeChatPushService(
            app_id="test_app",
            app_secret="test_secret",
            on_log=on_log,
        )
        service._client = mock_client

        with patch("asyncio.sleep", new_callable=AsyncMock):
            await service.send_text(
                "oABC123",
                "test",
                push_type=PushType.TASK_CREATED,
                task_id=1,
            )

        assert len(log_records) == 1
        assert log_records[0].success is False
        assert "43004" in (log_records[0].error or "")
        assert log_records[0].retries == 2  # All 3 attempts failed

    @pytest.mark.asyncio
    async def test_on_log_not_set_no_error(self):
        """Test: service works without on_log callback."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test-token",
            "expires_in": 7200,
        }
        send_resp = MagicMock()
        send_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}

        mock_client.get.return_value = token_resp
        mock_client.post.return_value = send_resp

        service = WeChatPushService(
            app_id="test_app",
            app_secret="test_secret",
        )
        service._client = mock_client

        # Should not raise even without on_log
        result = await service.send_text("oABC123", "test")
        assert result.success is True

    @pytest.mark.asyncio
    async def test_on_log_exception_isolated(self):
        """Test: exception in on_log doesn't affect push result."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test-token",
            "expires_in": 7200,
        }
        send_resp = MagicMock()
        send_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}

        mock_client.get.return_value = token_resp
        mock_client.post.return_value = send_resp

        async def broken_on_log(log):
            raise RuntimeError("DB connection lost")

        service = WeChatPushService(
            app_id="test_app",
            app_secret="test_secret",
            on_log=broken_on_log,
        )
        service._client = mock_client

        # Should not raise even with broken on_log
        result = await service.send_text("oABC123", "test")
        assert result.success is True


# ─────────────────────────────────────────────────────────────────────────────
# WeChatPushService - PushType enum tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPushType:
    def test_push_type_values(self):
        assert PushType.TASK_CREATED == "TASK_CREATED"
        assert PushType.TASK_ASSIGNED == "TASK_ASSIGNED"
        assert PushType.TASK_COMPLETED == "TASK_COMPLETED"

    def test_push_type_enum_members(self):
        assert len(PushType) == 3
