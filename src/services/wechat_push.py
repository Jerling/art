"""WeChat customer service message push service.

Implements the WeChat customer service API for sending text messages
to users after task creation.

API docs:
  - access_token: https://developers.weixin.qq.com/doc/offiaccount/Basic_Information/Get_access_token.html
  - custom message: https://developers.weixin.qq.com/doc/offiaccount/Message_Management/Service_Center_messages.html

The access_token is cached with automatic refresh (WeChat validity: 2 hours).
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

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


_token_cache = TokenCache()


# ─────────────────────────────────────────────────────────────────────────────
# Push result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class PushResult:
    """Result of a WeChat push attempt."""
    success: bool
    error: str | None = None
    msg_id: str | None = None
    latency_ms: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# WeChat Push Service
# ─────────────────────────────────────────────────────────────────────────────

class WeChatPushService:
    """Send WeChat customer service messages to users.

    Uses the WeChat custom message API to reply to users
    who sent a message to the official account.

    Usage:
        service = WeChatPushService()
        result = await service.send_text(openid="oABC123", text="✅ 任务已创建：...")
        if result.success:
            print(f"Message sent: {result.msg_id}")
    """

    BASE_URL = "https://api.weixin.qq.com/cgi-bin"

    def __init__(
        self,
        *,
        app_id: str | None = None,
        app_secret: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._app_id = app_id
        self._app_secret = app_secret
        self._client = http_client

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
    ) -> PushResult:
        """Send a text message to a specific WeChat user.

        Args:
            openid: The recipient's WeChat OpenID.
            text: The message text content (max 2048 bytes).

        Returns:
            PushResult with success status and optional error message.
        """
        # Resolve credentials (lazy — may read config on first call)
        app_id, app_secret = await self._resolve_credentials()
        if not app_id or not app_secret:
            logger.warning(
                "[wechat_push] WeChat AppID/AppSecret not configured — "
                "push skipped (openid=%s)", openid
            )
            return PushResult(
                success=False,
                error="WeChat AppID/AppSecret not configured",
            )

        start = time.perf_counter()

        # Step 1: Get (or refresh) access_token
        token = await self._get_access_token()
        if not token:
            return PushResult(
                success=False,
                error="Failed to obtain access_token",
                latency_ms=(time.perf_counter() - start) * 1000,
            )

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
                    "[wechat_push] Message sent to %s (%.0fms)",
                    openid,
                    elapsed_ms,
                )
                return PushResult(
                    success=True,
                    msg_id=str(data.get("msgid", "")),
                    latency_ms=elapsed_ms,
                )
            else:
                errmsg = data.get("errmsg", "unknown error")
                logger.error(
                    "[wechat_push] Send failed: errcode=%d errmsg=%s",
                    errcode,
                    errmsg,
                )
                # Token might be expired — invalidate cache on 40001/40014
                if errcode in (40001, 40014):
                    _token_cache.token = ""
                    _token_cache.expires_at = 0.0
                return PushResult(
                    success=False,
                    error=f"errcode={errcode}: {errmsg}",
                    latency_ms=elapsed_ms,
                )
        except httpx.TimeoutException:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "[wechat_push] Timeout sending to %s (%.0fms)", openid, elapsed_ms
            )
            return PushResult(
                success=False,
                error="HTTP timeout",
                latency_ms=elapsed_ms,
            )
        except httpx.HTTPError as exc:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "[wechat_push] HTTP error sending to %s: %s", openid, exc
            )
            return PushResult(
                success=False,
                error=f"HTTP error: {exc}",
                latency_ms=elapsed_ms,
            )

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
