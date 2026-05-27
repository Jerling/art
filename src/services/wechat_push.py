"""WeChat customer service message push service.

Implements the WeChat customer service API for sending text messages
to users on task creation, assignment, and completion.

API docs:
  - access_token: https://developers.weixin.qq.com/doc/offiaccount/Basic_Information/Get_access_token.html
  - custom message: https://developers.weixin.qq.com/doc/offiaccount/Message_Management/Service_Center_messages.html

The access_token is cached with automatic refresh (WeChat validity: 2 hours).

Sprint 3 enhancements:
  - Task assignment notification (assigned trigger)
  - Task completion notification (completed trigger)
  - Retry with exponential backoff (3 retries)
  - Push log database recording
  - Simple rate limiter
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Token cache
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TokenCache:
    """WeChat access_token cache with automatic expiry.

    TODO: This in-memory cache is per-process only. For multi-worker
    deployments (e.g. gunicorn with multiple uvicorn workers), each
    process will maintain its own cache, causing redundant token
    refreshes and potential rate limiting by WeChat. Replace with
    a shared cache (e.g. Redis) in production multi-worker setups.
    """

    token: str = ""
    expires_at: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    @property
    def is_valid(self) -> bool:
        """Return True if the cached token is still valid (with 5-min buffer)."""
        return bool(self.token and time.time() < (self.expires_at - 300))


# TODO(S4): This in-memory token cache does not work across multiple worker
# processes (e.g. uvicorn --workers 4). Each process has its own copy of
# _token_cache, leading to redundant token requests and potential rate limiting.
# Fix: use a shared cache (Redis or file-based lock) in a future sprint.
_token_cache = TokenCache()


# ─────────────────────────────────────────────────────────────────────────────
# Rate limiter (S3 suggestion)
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class RateLimiter:
    """Simple token-bucket rate limiter for WeChat API calls.

    WeChat custom message API has a rate limit of ~2000 calls/minute per account.
    We conservatively allow 30 calls/second (1800/min) to stay well under the limit.
    """

    max_tokens: float = 30.0
    refill_rate: float = 30.0  # tokens per second
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __post_init__(self) -> None:
        self._tokens = self.max_tokens
        self._last_refill = time.monotonic()

    async def acquire(self) -> None:
        """Acquire a token, waiting if necessary."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self.max_tokens, self._tokens + elapsed * self.refill_rate)
            self._last_refill = now

            if self._tokens < 1.0:
                wait_time = (1.0 - self._tokens) / self.refill_rate
                logger.debug("[wechat_push] rate limiter: waiting %.2fs", wait_time)
                await asyncio.sleep(wait_time)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


_rate_limiter = RateLimiter()


def _record_push_metric(push_type: str, success: bool) -> None:
    """Increment the Prometheus push_results_total counter.

    This is a module-level helper so it can be called without importing
    the metrics module at the point of use (avoids circular imports).
    """
    from src.observability.metrics import push_results_total

    result_label = "success" if success else "failure"
    push_results_total.labels(push_type=push_type, result=result_label).inc()


# ── Push result + log ────────────────────────────────────────────────────────


class PushType(str, Enum):
    """Type of push notification."""
    TASK_CREATED = "TASK_CREATED"
    TASK_ASSIGNED = "TASK_ASSIGNED"
    TASK_COMPLETED = "TASK_COMPLETED"


@dataclass
class PushResult:
    """Result of a WeChat push attempt."""
    success: bool
    error: str | None = None
    msg_id: str | None = None
    latency_ms: float = 0.0
    retries: int = 0


@dataclass
class PushLog:
    """Record of a push attempt for database persistence."""
    push_type: str
    openid: str
    task_id: int | None
    success: bool
    error: str | None = None
    msg_id: str | None = None
    latency_ms: float = 0.0
    retries: int = 0
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ─────────────────────────────────────────────────────────────────────────────
# WeChat Push Service
# ─────────────────────────────────────────────────────────────────────────────

class WeChatPushService:
    """Send WeChat customer service messages to users.

    Uses the WeChat custom message API to reply to users
    who sent a message to the official account.

    Sprint 3 features:
    - send_text() with automatic retry (3 attempts, exponential backoff)
    - send_task_assigned() for task assignment notifications
    - send_task_completed() for task completion notifications
    - Push logging via on_log callback
    - Rate limiting via token bucket

    Usage:
        service = WeChatPushService()
        result = await service.send_text(openid="oABC123", text="✅ 任务已创建：...")
        if result.success:
            print(f"Message sent: {result.msg_id}")
    """

    BASE_URL = "https://api.weixin.qq.com/cgi-bin"
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 1.0  # seconds

    def __init__(
        self,
        *,
        app_id: str | None = None,
        app_secret: str | None = None,
        http_client: httpx.AsyncClient | None = None,
        on_log: Callable[[PushLog], Awaitable[None] | None] | None = None,
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._client = http_client
        self._on_log = on_log

    async def _resolve_credentials(self) -> tuple[str, str]:
        """Resolve app_id and app_secret from args or config (lazy)."""
        from src.utils.config import get_config

        app_id = self._app_id
        app_secret = self._app_secret
        if not app_id or not app_secret:
            cfg = get_config().wechat
            app_id = app_id or cfg.app_id
            app_secret = app_secret or cfg.app_secret
        return app_id, app_secret

    async def send_text(
        self,
        openid: str,
        text: str,
        *,
        push_type: PushType = PushType.TASK_CREATED,
        task_id: int | None = None,
    ) -> PushResult:
        """Send a text message to a specific WeChat user.

        Includes automatic retry with exponential backoff (up to 3 attempts).

        Args:
            openid: The recipient's WeChat OpenID.
            text: The message text content (max 2048 bytes).
            push_type: Type of push notification (for logging).
            task_id: Associated task ID (for logging).

        Returns:
            PushResult with success status and optional error message.
        """
        # Resolve credentials (lazy — may read config on first call)
        app_id, app_secret = await self._resolve_credentials()
        if not app_id or not app_secret:
            logger.warning(
                "[wechat_push] WeChat AppID/AppSecret not configured — "
                "push skipped (openid=%s)",
                openid,
            )
            result = PushResult(
                success=False,
                error="WeChat AppID/AppSecret not configured",
            )
            await self._record_log(push_type, openid, task_id, result)
            _record_push_metric(push_type.value, result.success)
            return result

        start = time.perf_counter()
        last_error = ""

        for attempt in range(self.MAX_RETRIES):
            # Rate limit before each attempt
            await _rate_limiter.acquire()

            # Step 1: Get (or refresh) access_token
            token = await self._get_access_token()
            if not token:
                last_error = "Failed to obtain access_token"
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(
                        "[wechat_push] attempt %d/%d: token fetch failed, retrying in %.1fs",
                        attempt + 1,
                        self.MAX_RETRIES,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                break

            # Step 2: Send custom message
            url = f"{self.BASE_URL}/message/custom/send"
            params = {"access_token": token}
            payload = {
                "touser": openid,
                "msgtype": "text",
                "text": {"content": text[:2048]},
            }

            try:
                client = await self._get_client()
                resp = await client.post(url, params=params, json=payload)
                elapsed_ms = (time.perf_counter() - start) * 1000

                data = resp.json()
                errcode = data.get("errcode", 0)

                if errcode == 0:
                    logger.info(
                        "[wechat_push] Message sent to %s (%.0fms, attempt %d/%d)",
                        openid,
                        elapsed_ms,
                        attempt + 1,
                        self.MAX_RETRIES,
                    )
                    result = PushResult(
                        success=True,
                        msg_id=str(data.get("msgid", "")),
                        latency_ms=elapsed_ms,
                        retries=attempt,
                    )
                    await self._record_log(push_type, openid, task_id, result)
                    _record_push_metric(push_type.value, result.success)
                    return result
                else:
                    errmsg = data.get("errmsg", "unknown error")
                    last_error = f"errcode={errcode}: {errmsg}"
                    logger.error(
                        "[wechat_push] attempt %d/%d failed: errcode=%d errmsg=%s",
                        attempt + 1,
                        self.MAX_RETRIES,
                        errcode,
                        errmsg,
                    )
                    # Token might be expired — invalidate cache on 40001/40014
                    if errcode in (40001, 40014):
                        _token_cache.token = ""
                        _token_cache.expires_at = 0.0

                    if attempt < self.MAX_RETRIES - 1:
                        delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                        logger.info(
                            "[wechat_push] retrying in %.1fs (%d/%d)",
                            delay,
                            attempt + 1,
                            self.MAX_RETRIES,
                        )
                        await asyncio.sleep(delay)

            except httpx.TimeoutException:
                elapsed_ms = (time.perf_counter() - start) * 1000
                last_error = "HTTP timeout"
                logger.error(
                    "[wechat_push] attempt %d/%d timeout sending to %s (%.0fms)",
                    attempt + 1,
                    self.MAX_RETRIES,
                    openid,
                    elapsed_ms,
                )
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                    await asyncio.sleep(delay)

            except httpx.HTTPError as exc:
                elapsed_ms = (time.perf_counter() - start) * 1000
                last_error = f"HTTP error: {exc}"
                logger.error(
                    "[wechat_push] attempt %d/%d HTTP error sending to %s: %s",
                    attempt + 1,
                    self.MAX_RETRIES,
                    openid,
                    exc,
                )
                if attempt < self.MAX_RETRIES - 1:
                    delay = self.RETRY_BASE_DELAY * (2 ** attempt)
                    await asyncio.sleep(delay)

        # All retries exhausted
        elapsed_ms = (time.perf_counter() - start) * 1000
        result = PushResult(
            success=False,
            error=last_error,
            latency_ms=elapsed_ms,
            retries=self.MAX_RETRIES - 1,
        )
        await self._record_log(push_type, openid, task_id, result)
        _record_push_metric(push_type.value, result.success)
        return result

    async def send_task_assigned(
        self,
        openid: str,
        task_id: int,
        task_title: str,
        role_name: str,
    ) -> PushResult:
        """Send a task assignment notification to the assigned user.

        Args:
            openid: The assignee's WeChat OpenID.
            task_id: The task ID.
            task_title: The task title.
            role_name: The role name of the assignee.

        Returns:
            PushResult with success status.
        """
        text = (
            f"📋 新任务分配\n"
            f"「{task_title}」\n"
            f"你被分配为「{role_name}」\n"
            f"请及时处理"
        )
        return await self.send_text(
            openid,
            text,
            push_type=PushType.TASK_ASSIGNED,
            task_id=task_id,
        )

    async def send_task_completed(
        self,
        openid: str,
        task_id: int,
        task_title: str,
    ) -> PushResult:
        """Send a task completion notification to the task creator.

        Args:
            openid: The creator's WeChat OpenID.
            task_id: The task ID.
            task_title: The task title.

        Returns:
            PushResult with success status.
        """
        text = (
            f"✅ 任务已完成\n"
            f"「{task_title}」\n"
            f"状态已更新为完成"
        )
        return await self.send_text(
            openid,
            text,
            push_type=PushType.TASK_COMPLETED,
            task_id=task_id,
        )

    async def _record_log(
        self,
        push_type: PushType,
        openid: str,
        task_id: int | None,
        result: PushResult,
    ) -> None:
        """Record a push attempt to the database via the on_log callback."""
        log = PushLog(
            push_type=push_type.value,
            openid=openid,
            task_id=task_id,
            success=result.success,
            error=result.error,
            msg_id=result.msg_id,
            latency_ms=result.latency_ms,
            retries=result.retries,
        )
        if self._on_log is not None:
            try:
                import asyncio as _asyncio

                maybe_coro = self._on_log(log)
                if _asyncio.iscoroutine(maybe_coro):
                    await maybe_coro
            except Exception as exc:
                logger.error("[wechat_push] on_log callback failed: %s", exc)

    async def _get_access_token(self) -> str:
        """Get a valid access_token, refreshing if necessary.

        Uses the in-memory cache with a 5-minute buffer before expiry.
        Thread-safe via asyncio.Lock.
        """
        if _token_cache.is_valid:
            return _token_cache.token

        async with _token_cache.lock:
            # Double-check after acquiring lock
            if _token_cache.is_valid:
                return _token_cache.token

            app_id, app_secret = await self._resolve_credentials()
            url = f"{self.BASE_URL}/token"
            params = {
                "grant_type": "client_credential",
                "appid": app_id,
                "secret": app_secret,
            }

            try:
                client = await self._get_client()
                resp = await client.get(url, params=params)
                data = resp.json()

                if "access_token" in data:
                    _token_cache.token = data["access_token"]
                    _token_cache.expires_at = (
                        time.time() + data.get("expires_in", 7200)
                    )
                    logger.info(
                        "[wechat_push] access_token refreshed (expires_in=%ds)",
                        data.get("expires_in", 7200),
                    )
                    return _token_cache.token
                else:
                    errcode = data.get("errcode", "?")
                    errmsg = data.get("errmsg", "unknown")
                    logger.error(
                        "[wechat_push] Token request failed: %d %s",
                        errcode,
                        errmsg,
                    )
                    return ""
            except Exception as exc:
                logger.error(
                    "[wechat_push] Token request exception: %s", exc
                )
                return ""

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the shared HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
