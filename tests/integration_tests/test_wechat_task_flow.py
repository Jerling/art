"""End-to-end tests for the WeChat message → task auto-creation flow.

Tests the complete pipeline:
  1. WeChat message received via webhook (POST /wechat/webhook)
  2. Message persisted to DB
  3. Intent parsed via LLM (mocked)
  4. Task created via TaskService
  5. WeChat push notification sent (mocked)

Run with:
  pytest tests/integration_tests/test_wechat_task_flow.py -v --cov=src --cov-report=term-missing
"""
from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from src.domain.intent import IntentAction, IntentData, TaskPriority
from src.services.intent import IntentResult, IntentService
from src.services.task import TaskService
from src.services.wechat_push import PushResult, WeChatPushService


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_create_task_intent(
    title: str = "完成 API 设计",
    raw_text: str = "下周三前完成 API 设计",
    priority: TaskPriority = TaskPriority.HIGH,
    estimated_hours: float = 4.0,
    confidence: float = 0.92,
) -> IntentData:
    """Helper: build a CREATE_TASK IntentData."""
    return IntentData(
        action=IntentAction.CREATE_TASK,
        title=title,
        raw_text=raw_text,
        suggested_priority=priority,
        estimated_hours=estimated_hours,
        confidence=confidence,
    )


def _make_unknown_intent(raw_text: str = "你好") -> IntentData:
    """Helper: build an UNKNOWN IntentData."""
    return IntentData(
        action=IntentAction.UNKNOWN,
        raw_text=raw_text,
        confidence=0.0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# IntentService unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestIntentService:
    """Tests for IntentService.process_message()."""

    @pytest.fixture
    def mock_task_service(self) -> AsyncMock:
        """Create a mock TaskService."""
        svc = AsyncMock(spec=TaskService)
        return svc

    @pytest.fixture
    def intent_service(self, mock_task_service: AsyncMock) -> IntentService:
        """Create an IntentService with a mocked TaskService."""
        return IntentService(mock_task_service)

    @pytest.mark.asyncio
    async def test_create_task_flow(
        self,
        intent_service: IntentService,
        mock_task_service: AsyncMock,
    ):
        """Test: CREATE_TASK intent → task created → reply text generated."""
        intent = _make_create_task_intent()
        mock_task = MagicMock()
        mock_task.id = 42
        mock_task.title = "完成 API 设计"
        mock_task.priority = "HIGH"
        mock_task.estimated_hours = 4.0
        mock_task_service.create.return_value = mock_task

        with patch(
            "src.services.intent.analyze_intent",
            new_callable=AsyncMock,
            return_value=intent,
        ):
            result = await intent_service.process_message(
                "下周三前完成 API 设计", openid="oABC123"
            )

        assert result.action == IntentAction.CREATE_TASK
        assert result.task_created is True
        assert result.task_id == 42
        assert result.task_title == "完成 API 设计"
        assert result.reply_text is not None
        assert "✅ 任务已创建" in result.reply_text
        assert "完成 API 设计" in result.reply_text
        mock_task_service.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_intent_flow(
        self,
        intent_service: IntentService,
        mock_task_service: AsyncMock,
    ):
        """Test: UNKNOWN intent → no task created → fallback reply."""
        intent = _make_unknown_intent("你好")

        with patch(
            "src.services.intent.analyze_intent",
            new_callable=AsyncMock,
            return_value=intent,
        ):
            result = await intent_service.process_message("你好", openid="oABC123")

        assert result.action == IntentAction.UNKNOWN
        assert result.task_created is False
        assert result.task_id is None
        assert result.reply_text is not None
        assert "无法理解" in result.reply_text
        mock_task_service.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_llm_failure_returns_unknown(
        self,
        intent_service: IntentService,
        mock_task_service: AsyncMock,
    ):
        """Test: LLM failure → graceful UNKNOWN → fallback reply."""
        from src.llm.base import LLMError

        with patch(
            "src.services.intent.analyze_intent",
            new_callable=AsyncMock,
            side_effect=LLMError("timeout"),
        ):
            result = await intent_service.process_message(
                "some message", openid="oABC123"
            )

        assert result.action == IntentAction.UNKNOWN
        assert result.task_created is False
        assert result.reply_text is not None
        assert "无法理解" in result.reply_text
        mock_task_service.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_task_creation_failure(
        self,
        intent_service: IntentService,
        mock_task_service: AsyncMock,
    ):
        """Test: TaskService.create() fails → graceful error reply."""
        intent = _make_create_task_intent()
        mock_task_service.create.side_effect = ValueError("DB constraint violation")

        with patch(
            "src.services.intent.analyze_intent",
            new_callable=AsyncMock,
            return_value=intent,
        ):
            result = await intent_service.process_message(
                "下周三前完成 API 设计", openid="oABC123"
            )

        assert result.task_created is False
        assert result.reply_text is not None
        assert "任务创建失败" in result.reply_text

    @pytest.mark.asyncio
    async def test_create_task_with_priority_mapping(
        self,
        intent_service: IntentService,
        mock_task_service: AsyncMock,
    ):
        """Test: Intent priority is correctly mapped to Task priority."""
        intent = _make_create_task_intent(priority=TaskPriority.URGENT)
        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.title = "紧急任务"
        mock_task.priority = "URGENT"
        mock_task.estimated_hours = 1.0
        mock_task_service.create.return_value = mock_task

        with patch(
            "src.services.intent.analyze_intent",
            new_callable=AsyncMock,
            return_value=intent,
        ):
            result = await intent_service.process_message(
                "紧急任务", openid="oABC123"
            )

        assert result.task_created is True
        # Verify the TaskCreate data that was passed to TaskService.create
        call_args = mock_task_service.create.call_args
        task_create = call_args[0][0]
        assert task_create.priority.value == "URGENT"

    @pytest.mark.asyncio
    async def test_create_task_without_title_uses_raw_text(
        self,
        intent_service: IntentService,
        mock_task_service: AsyncMock,
    ):
        """Test: CREATE_TASK without title → uses raw_text as fallback."""
        intent = IntentData(
            action=IntentAction.CREATE_TASK,
            title=None,
            raw_text="下周三前完成 API 设计",
            suggested_priority=TaskPriority.HIGH,
            estimated_hours=4.0,
            confidence=0.92,
        )
        mock_task = MagicMock()
        mock_task.id = 1
        mock_task.title = "下周三前完成 API 设计"
        mock_task.priority = "HIGH"
        mock_task.estimated_hours = 4.0
        mock_task_service.create.return_value = mock_task

        with patch(
            "src.services.intent.analyze_intent",
            new_callable=AsyncMock,
            return_value=intent,
        ):
            result = await intent_service.process_message(
                "下周三前完成 API 设计", openid="oABC123"
            )

        assert result.task_created is True
        call_args = mock_task_service.create.call_args
        task_create = call_args[0][0]
        assert task_create.title == "下周三前完成 API 设计"

    @pytest.mark.asyncio
    async def test_query_task_returns_placeholder(
        self,
        intent_service: IntentService,
        mock_task_service: AsyncMock,
    ):
        """Test: QUERY_TASK intent → placeholder reply."""
        intent = IntentData(
            action=IntentAction.QUERY_TASK,
            raw_text="查看我的任务",
            confidence=0.95,
        )

        with patch(
            "src.services.intent.analyze_intent",
            new_callable=AsyncMock,
            return_value=intent,
        ):
            result = await intent_service.process_message(
                "查看我的任务", openid="oABC123"
            )

        assert result.action == IntentAction.QUERY_TASK
        assert result.task_created is False
        assert result.reply_text is not None
        assert "任务查询" in result.reply_text
        mock_task_service.create.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# WeChatPushService unit tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWeChatPushService:
    """Tests for WeChatPushService."""

    @pytest.mark.asyncio
    async def test_send_text_success(self):
        """Test: successful text message push."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        # Token response
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test-token-123",
            "expires_in": 7200,
        }
        # Send response
        send_resp = MagicMock()
        send_resp.json.return_value = {"errcode": 0, "errmsg": "ok", "msgid": "msg_456"}

        mock_client.get.return_value = token_resp
        mock_client.post.return_value = send_resp

        service = WeChatPushService(
            app_id="test_app_id",
            app_secret="test_app_secret",
        )
        service._client = mock_client

        result = await service.send_text("oABC123", "✅ 任务已创建：测试任务")

        assert result.success is True
        assert result.msg_id == "msg_456"
        assert result.error is None

    @pytest.mark.asyncio
    async def test_send_text_wechat_not_configured(self):
        """Test: push skipped when AppID/Secret not configured."""
        mock_client = AsyncMock()
        service = WeChatPushService(
            app_id="",
            app_secret="",
        )
        service._client = mock_client

        # Patch get_config to avoid JWT_SECRET_KEY requirement
        with patch("src.utils.config.get_config") as mock_cfg:
            mock_cfg.return_value.wechat.app_id = ""
            mock_cfg.return_value.wechat.app_secret = ""
            result = await service.send_text("oABC123", "test message")

        assert result.success is False
        assert result.error is not None
        assert "not configured" in result.error
        mock_client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_text_api_error(self):
        """Test: WeChat API returns error code."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test-token",
            "expires_in": 7200,
        }
        send_resp = MagicMock()
        send_resp.json.return_value = {
            "errcode": 43004,
            "errmsg": "require subscribe",
        }

        mock_client.get.return_value = token_resp
        mock_client.post.return_value = send_resp

        service = WeChatPushService(
            app_id="test_app_id",
            app_secret="test_app_secret",
        )
        service._client = mock_client

        result = await service.send_text("oABC123", "test")

        assert result.success is False
        assert result.error is not None
        assert "43004" in result.error

    @pytest.mark.asyncio
    async def test_send_text_timeout(self):
        """Test: HTTP timeout → graceful failure."""
        import httpx

        mock_client = AsyncMock()
        mock_client.is_closed = False
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "test-token",
            "expires_in": 7200,
        }
        mock_client.get.return_value = token_resp
        mock_client.post.side_effect = httpx.TimeoutException("timeout")

        service = WeChatPushService(
            app_id="test_app_id",
            app_secret="test_app_secret",
        )
        service._client = mock_client

        result = await service.send_text("oABC123", "test")

        assert result.success is False
        assert result.error is not None
        err_lower = result.error.lower()
        assert "timeout" in err_lower or "http" in err_lower

    @pytest.mark.asyncio
    async def test_token_caching(self):
        """Test: access_token is cached and reused."""
        # Reset the module-level token cache to ensure a fresh start
        from src.services.wechat_push import _token_cache
        _token_cache.token = ""
        _token_cache.expires_at = 0.0

        mock_client = AsyncMock()
        mock_client.is_closed = False
        token_resp = MagicMock()
        token_resp.json.return_value = {
            "access_token": "cached-token",
            "expires_in": 7200,
        }
        send_resp = MagicMock()
        send_resp.json.return_value = {"errcode": 0, "errmsg": "ok"}

        mock_client.get.return_value = token_resp
        mock_client.post.return_value = send_resp

        service = WeChatPushService(
            app_id="test_app_id",
            app_secret="test_app_secret",
        )
        service._client = mock_client

        # First call — should fetch token
        await service.send_text("oABC123", "msg1")
        # Second call — should reuse cached token
        await service.send_text("oABC123", "msg2")

        # Token endpoint should only be called once
        assert mock_client.get.call_count == 1
        # But message send should be called twice
        assert mock_client.post.call_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# Webhook integration tests (mocked LLM + push)
# ─────────────────────────────────────────────────────────────────────────────

class TestWebhookTaskFlow:
    """Integration tests for POST /wechat/webhook → task creation flow.

    These tests use the FastAPI TestClient with mocked LLM and push services
    to verify the complete end-to-end flow.
    """

    @pytest.fixture
    def mock_glm_provider(self) -> AsyncMock:
        """Create a mock GLM provider."""
        provider = AsyncMock()
        provider.close = AsyncMock()
        return provider

    @pytest.mark.asyncio
    async def test_webhook_creates_task_and_pushes(
        self, mock_glm_provider: AsyncMock
    ):
        """Test: webhook receives message → task created → push sent."""
        from main import app

        # Build a valid WeChat XML message (plaintext mode)
        xml_body = (
            "<xml>"
            "<ToUserName>gh_xyz</ToUserName>"
            "<FromUserName>oABC123</FromUserName>"
            "<CreateTime>1716300000</CreateTime>"
            "<MsgType>text</MsgType>"
            "<Content>下周三前完成 API 设计</Content>"
            "<MsgId>1234567890</MsgId>"
            "</xml>"
        )

        # Mock the intent parsing
        intent = _make_create_task_intent()

        # Create a mock task
        mock_task = MagicMock()
        mock_task.id = 42
        mock_task.title = "完成 API 设计"
        mock_task.priority = "HIGH"
        mock_task.estimated_hours = 4.0

        with patch(
            "src.api.handlers.wechat.IntentService"
        ) as MockIntentService, patch(
            "src.api.handlers.wechat.WeChatPushService"
        ) as MockPushService, patch(
            "src.api.handlers.wechat._build_crypto"
        ) as mock_crypto, patch(
            "src.api.handlers.wechat.WeChatMessageStore"
        ) as MockStore:
            mock_crypto.return_value.verify_signature.return_value = True
            mock_store_instance = AsyncMock()
            mock_store_instance.save = AsyncMock()
            MockStore.return_value = mock_store_instance
            mock_intent_svc = AsyncMock()
            mock_intent_svc.process_message.return_value = IntentResult(
                intent=intent,
                task_created=True,
                task_id=42,
                task_title="完成 API 设计",
                task_priority="HIGH",
                task_estimated_hours=4.0,
                reply_text="✅ 任务已创建：「完成 API 设计」\n优先级 HIGH，预计 4.0h",
            )
            MockIntentService.return_value = mock_intent_svc

            mock_push_svc = AsyncMock()
            mock_push_svc.send_text.return_value = PushResult(
                success=True, msg_id="msg_789"
            )
            mock_push_svc.close = AsyncMock()
            MockPushService.return_value = mock_push_svc

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/wechat/webhook",
                    params={
                        "signature": "valid_sig",
                        "timestamp": "1716300000",
                        "nonce": "test_nonce",
                        "msg_signature": "valid_msg_sig",
                    },
                    content=xml_body.encode("utf-8"),
                    headers={"Content-Type": "application/xml"},
                )

        assert response.status_code == 200
        mock_intent_svc.process_message.assert_called_once()
        mock_push_svc.send_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_webhook_unknown_intent_sends_fallback(
        self, mock_glm_provider: AsyncMock
    ):
        """Test: webhook receives unknown message → fallback reply pushed."""
        from main import app

        xml_body = (
            "<xml>"
            "<ToUserName>gh_xyz</ToUserName>"
            "<FromUserName>oABC123</FromUserName>"
            "<CreateTime>1716300000</CreateTime>"
            "<MsgType>text</MsgType>"
            "<Content>你好</Content>"
            "<MsgId>9876543210</MsgId>"
            "</xml>"
        )

        intent = _make_unknown_intent("你好")

        with patch(
            "src.api.handlers.wechat.IntentService"
        ) as MockIntentService, patch(
            "src.api.handlers.wechat.WeChatPushService"
        ) as MockPushService, patch(
            "src.api.handlers.wechat._build_crypto"
        ) as mock_crypto, patch(
            "src.api.handlers.wechat.WeChatMessageStore"
        ) as MockStore:
            mock_crypto.return_value.verify_signature.return_value = True
            mock_store_instance = AsyncMock()
            mock_store_instance.save = AsyncMock()
            MockStore.return_value = mock_store_instance
            mock_intent_svc = AsyncMock()
            mock_intent_svc.process_message.return_value = IntentResult(
                intent=intent,
                task_created=False,
                reply_text="无法理解，请换一种说法。",
            )
            MockIntentService.return_value = mock_intent_svc

            mock_push_svc = AsyncMock()
            mock_push_svc.send_text.return_value = PushResult(
                success=True, msg_id="msg_fallback"
            )
            mock_push_svc.close = AsyncMock()
            MockPushService.return_value = mock_push_svc

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/wechat/webhook",
                    params={
                        "signature": "valid_sig",
                        "timestamp": "1716300000",
                        "nonce": "test_nonce",
                        "msg_signature": "valid_msg_sig",
                    },
                    content=xml_body.encode("utf-8"),
                    headers={"Content-Type": "application/xml"},
                )

        assert response.status_code == 200
        mock_intent_svc.process_message.assert_called_once()
        # Verify the fallback message was pushed
        call_args = mock_push_svc.send_text.call_args
        pushed_text = call_args[1].get("text", "") if call_args[1] else call_args[0][1] if len(call_args[0]) > 1 else ""
        assert "无法理解" in pushed_text

    @pytest.mark.asyncio
    async def test_webhook_push_failure_still_returns_200(
        self, mock_glm_provider: AsyncMock
    ):
        """Test: push failure doesn't break the 200 response."""
        from main import app

        xml_body = (
            "<xml>"
            "<ToUserName>gh_xyz</ToUserName>"
            "<FromUserName>oABC123</FromUserName>"
            "<CreateTime>1716300000</CreateTime>"
            "<MsgType>text</MsgType>"
            "<Content>下周三前完成 API 设计</Content>"
            "<MsgId>111111</MsgId>"
            "</xml>"
        )

        intent = _make_create_task_intent()

        with patch(
            "src.api.handlers.wechat.IntentService"
        ) as MockIntentService, patch(
            "src.api.handlers.wechat.WeChatPushService"
        ) as MockPushService, patch(
            "src.api.handlers.wechat._build_crypto"
        ) as mock_crypto, patch(
            "src.api.handlers.wechat.WeChatMessageStore"
        ) as MockStore:
            mock_crypto.return_value.verify_signature.return_value = True
            mock_store_instance = AsyncMock()
            mock_store_instance.save = AsyncMock()
            MockStore.return_value = mock_store_instance
            mock_intent_svc = AsyncMock()
            mock_intent_svc.process_message.return_value = IntentResult(
                intent=intent,
                task_created=True,
                task_id=1,
                task_title="完成 API 设计",
                task_priority="HIGH",
                task_estimated_hours=4.0,
                reply_text="✅ 任务已创建",
            )
            MockIntentService.return_value = mock_intent_svc

            mock_push_svc = AsyncMock()
            mock_push_svc.send_text.return_value = PushResult(
                success=False, error="WeChat not configured"
            )
            mock_push_svc.close = AsyncMock()
            MockPushService.return_value = mock_push_svc

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/wechat/webhook",
                    params={
                        "signature": "valid_sig",
                        "timestamp": "1716300000",
                        "nonce": "test_nonce",
                        "msg_signature": "valid_msg_sig",
                    },
                    content=xml_body.encode("utf-8"),
                    headers={"Content-Type": "application/xml"},
                )

        # Must still return 200 even if push fails
        assert response.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Task creation → WeChat push notification tests
# ─────────────────────────────────────────────────────────────────────────────
class TestTaskCreationPush:
    """Tests for POST /tasks with openid → WeChat push notification.

    When a task is created via the API with an openid field, the handler
    should trigger a best-effort WeChat push notification with the
    confirmation template.
    """

    def _make_mock_task(self, task_id=1, title="Test", priority="HIGH", estimated_hours: float | None = 4.0):
        """Helper: build a properly configured mock Task."""
        from datetime import datetime, timezone

        mock_task = MagicMock()
        mock_task.id = task_id
        mock_task.title = title
        mock_task.description = None
        mock_task.status = "PENDING"
        mock_task.priority = priority
        mock_task.estimated_hours = estimated_hours
        mock_task.created_at = datetime.now(timezone.utc)
        mock_task.updated_at = datetime.now(timezone.utc)
        return mock_task

    def _make_mock_service(self, mock_task):
        """Helper: build a properly configured mock TaskService."""
        mock_svc = AsyncMock()
        mock_svc.create = AsyncMock(return_value=mock_task)
        mock_svc._get_role_ids_for_task = AsyncMock(return_value=[])
        return mock_svc

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Set up and tear down dependency overrides."""
        from main import app
        app.dependency_overrides.clear()
        yield
        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_create_task_with_openid_pushes_notification(self):
        """Test: POST /tasks with openid → push notification sent."""
        from datetime import datetime, timezone
        from unittest.mock import AsyncMock, MagicMock, patch

        from httpx import ASGITransport, AsyncClient
        from main import app
        from src.api.handlers.task import get_task_service

        mock_task = self._make_mock_task(
            task_id=1, title="完成 API 设计", priority="HIGH", estimated_hours=4.0
        )
        mock_svc = self._make_mock_service(mock_task)
        app.dependency_overrides[get_task_service] = lambda: mock_svc

        with patch(
            "src.services.wechat_push.WeChatPushService"
        ) as MockPushService:
            mock_push = AsyncMock()
            mock_push.send_text.return_value = MagicMock(
                success=True, msg_id="msg_123", error=None
            )
            mock_push.close = AsyncMock()
            MockPushService.return_value = mock_push

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/tasks",
                    json={
                        "title": "完成 API 设计",
                        "priority": "HIGH",
                        "estimated_hours": 4.0,
                        "openid": "oABC123",
                    },
                )

            assert response.status_code == 201
            data = response.json()
            assert data["title"] == "完成 API 设计"
            assert data["priority"] == "HIGH"

            # Verify push was called with correct template
            mock_push.send_text.assert_called_once()
            call_kwargs = mock_push.send_text.call_args
            # send_text(openid=..., text=...)
            if call_kwargs.kwargs:
                assert call_kwargs.kwargs["openid"] == "oABC123"
                pushed_text = call_kwargs.kwargs["text"]
            else:
                # positional: send_text(openid, text)
                assert call_kwargs.args[0] == "oABC123"
                pushed_text = call_kwargs.args[1]

            assert "✅ 任务已创建" in pushed_text
            assert "完成 API 设计" in pushed_text
            assert "HIGH" in pushed_text
            assert "4.0h" in pushed_text

    @pytest.mark.asyncio
    async def test_create_task_without_openid_no_push(self):
        """Test: POST /tasks without openid → no push attempted."""
        from datetime import datetime, timezone
        from unittest.mock import AsyncMock, MagicMock, patch

        from httpx import ASGITransport, AsyncClient
        from main import app
        from src.api.handlers.task import get_task_service

        mock_task = self._make_mock_task(
            task_id=2, title="普通任务", priority="MEDIUM", estimated_hours=None
        )
        mock_svc = self._make_mock_service(mock_task)
        app.dependency_overrides[get_task_service] = lambda: mock_svc

        with patch(
            "src.services.wechat_push.WeChatPushService"
        ) as MockPushService:
            mock_push = AsyncMock()
            mock_push.close = AsyncMock()
            MockPushService.return_value = mock_push

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/tasks",
                    json={"title": "普通任务"},
                )

            assert response.status_code == 201
            # Push service should NOT have been instantiated
            MockPushService.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_task_push_failure_still_returns_201(self):
        """Test: push failure doesn't break the 201 response."""
        from datetime import datetime, timezone
        from unittest.mock import AsyncMock, MagicMock, patch

        from httpx import ASGITransport, AsyncClient
        from main import app
        from src.api.handlers.task import get_task_service

        mock_task = self._make_mock_task(
            task_id=3, title="测试任务", priority="LOW", estimated_hours=2.0
        )
        mock_svc = self._make_mock_service(mock_task)
        app.dependency_overrides[get_task_service] = lambda: mock_svc

        with patch(
            "src.services.wechat_push.WeChatPushService"
        ) as MockPushService:
            mock_push = AsyncMock()
            mock_push.send_text.return_value = MagicMock(
                success=False, error="WeChat not configured"
            )
            mock_push.close = AsyncMock()
            MockPushService.return_value = mock_push

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/tasks",
                    json={
                        "title": "测试任务",
                        "openid": "oXYZ789",
                    },
                )

            # Must still return 201 even if push fails
            assert response.status_code == 201
            data = response.json()
            assert data["title"] == "测试任务"

    @pytest.mark.asyncio
    async def test_create_task_push_without_estimated_hours(self):
        """Test: push message shows '未估算' when no estimated_hours."""
        from unittest.mock import AsyncMock, patch

        from httpx import ASGITransport, AsyncClient
        from main import app
        from src.api.handlers.task import get_task_service

        mock_task = self._make_mock_task(
            task_id=4, title="无估算任务", priority="MEDIUM", estimated_hours=None
        )
        mock_svc = self._make_mock_service(mock_task)
        app.dependency_overrides[get_task_service] = lambda: mock_svc

        with patch(
            "src.services.wechat_push.WeChatPushService"
        ) as MockPushService:
            mock_push = AsyncMock()
            mock_push.send_text.return_value = MagicMock(success=True)
            mock_push.close = AsyncMock()
            MockPushService.return_value = mock_push

            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/tasks",
                    json={
                        "title": "无估算任务",
                        "openid": "oNoHours",
                    },
                )

            assert response.status_code == 201
            mock_push.send_text.assert_called_once()
            call_kwargs = mock_push.send_text.call_args
            if call_kwargs.kwargs:
                pushed_text = call_kwargs.kwargs["text"]
            else:
                pushed_text = call_kwargs.args[1]

            assert "未估算" in pushed_text
