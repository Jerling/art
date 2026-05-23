"""MiniMax fault-tolerance test suite.

Covers 6 failure scenarios per Sprint 2 acceptance criteria:
1. Network timeout (ConnectTimeout, ReadTimeout)
2. HTTP 500 internal server error
3. HTTP 502/503 gateway errors
4. API Key invalid (401/403)
5. Response format anomaly (non-JSON body)
6. Rate limiting (429 Too Many Requests)

Each scenario verifies:
- No unhandled exception propagates
- Returns IntentAction.UNKNOWN (degraded result)
- Error log contains scenario marker

Target interface: src.llm.minimax.analyze_intent(text: str) -> IntentData
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any
from unittest.mock import MagicMock

import httpx
import pytest

from src.domain.intent import IntentAction, IntentData


# ─────────────────────────────────────────────────────────────────────────────
# Module import with clear error if integration not yet built
# ─────────────────────────────────────────────────────────────────────────────
try:
    from src.llm import minimax
except ImportError:  # pragma: no cover — parent t_843db13a not yet complete
    minimax = None  # type: ignore[assignment]


pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(minimax is None, reason="src.llm.minimax not yet built (t_843db13a pending)"),
]


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
_MINIMAX_BASE = "https://api.minimax.chat/v1"


class _SpyHandler(logging.Handler):
    """Captures log records for inspection."""

    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _make_spy_logger() -> tuple[logging.Logger, _SpyHandler]:
    logger = logging.getLogger("src.llm.minimax")
    handler = _SpyHandler()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    return logger, handler


def _assert_UNKNOWN(result: IntentData, msg: str = "") -> None:
    assert result.action == IntentAction.UNKNOWN, (
        f"{msg} — expected UNKNOWN, got {result.action!r}"
    )


def _assert_no_exception(result: Any, exc: Exception | None, msg: str = "") -> None:
    assert exc is None, f"{msg} — unexpected exception: {exc}"
    assert result is not None, f"{msg} — result must not be None"


def _assert_log_contains(handler: _SpyHandler, marker: str) -> None:
    """Verify at least one log record contains the scenario marker."""
    joined = "\n".join(r.getMessage() for r in handler.records)
    assert marker in joined, (
        f"log does not contain marker {marker!r}\n"
        f"logged messages:\n{joined}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Transport that replays canned responses / raises specified errors
# ─────────────────────────────────────────────────────────────────────────────
class _FaultTransport(httpx.BaseTransport):
    """httpx transport that simulates a named failure mode."""

    def __init__(
        self,
        *,
        failure: str,
        status_code: int = 500,
        response_body: str | None = None,
        response_headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__()
        self.failure = failure
        self.status_code = status_code
        self.response_body = response_body
        self.response_headers = response_headers or {}

    async def aclose(self) -> None:
        pass  # pragma: no cover

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        from httpx import ConnectTimeout, ReadTimeout

        if self.failure == "connect_timeout":
            raise ConnectTimeout("Connection timed out", request=request)
        if self.failure == "read_timeout":
            raise ReadTimeout("Read timed out", request=request)
        if self.failure == "http_error":
            return httpx.Response(
                status_code=self.status_code,
                content=self.response_body.encode() if self.response_body else b"",
                headers=self.response_headers,
                request=request,
            )
        if self.failure == "invalid_json":
            return httpx.Response(
                status_code=200,
                content=b"not valid json {{{",
                headers={"content-type": "application/json"},
                request=request,
            )
        # default: ok
        return httpx.Response(
            status_code=200,
            content=json.dumps({"choices": [{"message": {"content": '{"action":"list_tasks"}'}}]}).encode(),
            headers={"content-type": "application/json"},
            request=request,
        )


def _build_client(failure: str, status_code: int = 500, body: str | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=_MINIMAX_BASE,
        timeout=httpx.Timeout(30.0),
        transport=_FaultTransport(failure=failure, status_code=status_code, response_body=body),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Test cases — 6 failure scenarios
# ─────────────────────────────────────────────────────────────────────────────

async def test_connect_timeout_returns_UNKNOWN() -> None:
    """Scenario 1a: ConnectTimeout → IntentAction.UNKNOWN, no exception."""
    client = _build_client("connect_timeout")
    logger, handler = _make_spy_logger()

    exc: Exception | None = None
    result: IntentData | None = None
    try:
        provider = minimax.MiniMaxProvider(api_key="test-key-fault-injection")
        provider._client = client
        result = await minimax.analyze_intent("下周三前完成 API 设计", provider=provider)
    except Exception as e:
        exc = e

    _assert_no_exception(result, exc, "ConnectTimeout")
    _assert_UNKNOWN(result, "ConnectTimeout")
    _assert_log_contains(handler, "[minimax/failure/connect_timeout]")


async def test_read_timeout_returns_UNKNOWN() -> None:
    """Scenario 1b: ReadTimeout → IntentAction.UNKNOWN, no exception."""
    client = _build_client("read_timeout")
    logger, handler = _make_spy_logger()

    exc: Exception | None = None
    result: IntentData | None = None
    try:
        provider = minimax.MiniMaxProvider(api_key="test-key-fault-injection")
        provider._client = client
        result = await minimax.analyze_intent("下周三前完成 API 设计", provider=provider)
    except Exception as e:
        exc = e

    _assert_no_exception(result, exc, "ReadTimeout")
    _assert_UNKNOWN(result, "ReadTimeout")
    _assert_log_contains(handler, "[minimax/failure/read_timeout]")


async def test_http_500_returns_UNKNOWN() -> None:
    """Scenario 2: HTTP 500 → IntentAction.UNKNOWN, no exception."""
    client = _build_client("http_error", status_code=500)
    logger, handler = _make_spy_logger()

    exc: Exception | None = None
    result: IntentData | None = None
    try:
        provider = minimax.MiniMaxProvider(api_key="test-key-fault-injection")
        provider._client = client
        result = await minimax.analyze_intent("下周三前完成 API 设计", provider=provider)
    except Exception as e:
        exc = e

    _assert_no_exception(result, exc, "HTTP 500")
    _assert_UNKNOWN(result, "HTTP 500")
    _assert_log_contains(handler, "[minimax/failure/http_500]")


async def test_http_502_returns_UNKNOWN() -> None:
    """Scenario 3a: HTTP 502 → IntentAction.UNKNOWN, no exception."""
    client = _build_client("http_error", status_code=502)
    logger, handler = _make_spy_logger()

    exc: Exception | None = None
    result: IntentData | None = None
    try:
        provider = minimax.MiniMaxProvider(api_key="test-key-fault-injection")
        provider._client = client
        result = await minimax.analyze_intent("下周三前完成 API 设计", provider=provider)
    except Exception as e:
        exc = e

    _assert_no_exception(result, exc, "HTTP 502")
    _assert_UNKNOWN(result, "HTTP 502")
    _assert_log_contains(handler, "[minimax/failure/http_502]")


async def test_http_503_returns_UNKNOWN() -> None:
    """Scenario 3b: HTTP 503 → IntentAction.UNKNOWN, no exception."""
    client = _build_client("http_error", status_code=503)
    logger, handler = _make_spy_logger()

    exc: Exception | None = None
    result: IntentData | None = None
    try:
        provider = minimax.MiniMaxProvider(api_key="test-key-fault-injection")
        provider._client = client
        result = await minimax.analyze_intent("下周三前完成 API 设计", provider=provider)
    except Exception as e:
        exc = e

    _assert_no_exception(result, exc, "HTTP 503")
    _assert_UNKNOWN(result, "HTTP 503")
    _assert_log_contains(handler, "[minimax/failure/http_503]")


async def test_api_key_401_returns_UNKNOWN() -> None:
    """Scenario 4a: API Key invalid (401) → IntentAction.UNKNOWN, no exception."""
    client = _build_client("http_error", status_code=401)
    logger, handler = _make_spy_logger()

    exc: Exception | None = None
    result: IntentData | None = None
    try:
        provider = minimax.MiniMaxProvider(api_key="test-key-fault-injection")
        provider._client = client
        result = await minimax.analyze_intent("下周三前完成 API 设计", provider=provider)
    except Exception as e:
        exc = e

    _assert_no_exception(result, exc, "HTTP 401")
    _assert_UNKNOWN(result, "HTTP 401")
    _assert_log_contains(handler, "[minimax/failure/http_401]")


async def test_api_key_403_returns_UNKNOWN() -> None:
    """Scenario 4b: API Key forbidden (403) → IntentAction.UNKNOWN, no exception."""
    client = _build_client("http_error", status_code=403)
    logger, handler = _make_spy_logger()

    exc: Exception | None = None
    result: IntentData | None = None
    try:
        provider = minimax.MiniMaxProvider(api_key="test-key-fault-injection")
        provider._client = client
        result = await minimax.analyze_intent("下周三前完成 API 设计", provider=provider)
    except Exception as e:
        exc = e

    _assert_no_exception(result, exc, "HTTP 403")
    _assert_UNKNOWN(result, "HTTP 403")
    _assert_log_contains(handler, "[minimax/failure/http_403]")


async def test_non_json_response_returns_UNKNOWN() -> None:
    """Scenario 5: Non-JSON response body → IntentAction.UNKNOWN, no exception."""
    client = _build_client("invalid_json")
    logger, handler = _make_spy_logger()

    exc: Exception | None = None
    result: IntentData | None = None
    try:
        provider = minimax.MiniMaxProvider(api_key="test-key-fault-injection")
        provider._client = client
        result = await minimax.analyze_intent("下周三前完成 API 设计", provider=provider)
    except Exception as e:
        exc = e

    _assert_no_exception(result, exc, "Non-JSON")
    _assert_UNKNOWN(result, "Non-JSON")
    _assert_log_contains(handler, "[minimax/failure/invalid_json]")


async def test_rate_limit_429_returns_UNKNOWN() -> None:
    """Scenario 6: HTTP 429 → IntentAction.UNKNOWN, no exception."""
    client = _build_client("http_error", status_code=429)
    logger, handler = _make_spy_logger()

    exc: Exception | None = None
    result: IntentData | None = None
    try:
        provider = minimax.MiniMaxProvider(api_key="test-key-fault-injection")
        provider._client = client
        result = await minimax.analyze_intent("下周三前完成 API 设计", provider=provider)
    except Exception as e:
        exc = e

    _assert_no_exception(result, exc, "HTTP 429")
    _assert_UNKNOWN(result, "HTTP 429")
    _assert_log_contains(handler, "[minimax/failure/http_429]")
