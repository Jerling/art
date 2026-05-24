"""MiniMax fault-tolerance test suite.

Covers 6 failure scenarios per Sprint 2 acceptance criteria:
1. Network timeout (ConnectTimeout / ReadTimeout)
2. Server 5xx error (500, 502, 503)
3. API Key invalid (401 / 403)
4. Rate limiting (429 + Retry-After)
5. Response format anomaly (non-JSON body)
6. Response field missing (schema validation failure)

Each scenario verifies:
- No unhandled exception propagates
- Returns IntentAction.UNKNOWN (degraded result)
- Error log contains scenario marker
- Downstream consumers receive safe fallback → "服务暂时不可用"

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


def _assert_degraded_response(result: IntentData, text: str, msg: str = "") -> None:
    """Verify the degraded response is safe for downstream '服务暂时不可用' reply."""
    _assert_UNKNOWN(result, msg)
    # confidence may be None (Pydantic default) or 0.0 — both are safe degraded values
    assert result.confidence is None or result.confidence == 0.0, (
        f"{msg} — confidence should be None or 0.0 on degradation, got {result.confidence!r}"
    )
    assert result.raw_text == text, f"{msg} — raw_text should preserve original input"


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
        if self.failure == "missing_fields":
            # Valid JSON MiniMax format but inner content is missing required fields
            return httpx.Response(
                status_code=200,
                content=json.dumps({
                    "choices": [{"message": {"content": '{"partial": "data"}'}}]
                }).encode(),
                headers={"content-type": "application/json"},
                request=request,
            )
        if self.failure == "empty_choices":
            # Valid JSON but MiniMax returned empty choices array
            return httpx.Response(
                status_code=200,
                content=json.dumps({"choices": []}).encode(),
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


def _build_client(failure: str, status_code: int = 500, body: str | None = None,
                  headers: dict[str, str] | None = None) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=_MINIMAX_BASE,
        timeout=httpx.Timeout(30.0),
        transport=_FaultTransport(
            failure=failure,
            status_code=status_code,
            response_body=body,
            response_headers=headers,
        ),
    )


async def _run_with_fault(
    failure: str,
    text: str = "下周三前完成 API 设计",
    status_code: int = 500,
    body: str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[IntentData | None, Exception | None, _SpyHandler]:
    """Helper: run analyze_intent with a fault transport, return (result, exc, spy)."""
    client = _build_client(failure, status_code=status_code, body=body, headers=headers)
    _, handler = _make_spy_logger()

    exc: Exception | None = None
    result: IntentData | None = None
    try:
        provider = minimax.MiniMaxProvider(api_key="test-key-fault-injection")
        provider._client = client
        result = await minimax.analyze_intent(text, provider=provider)
    except Exception as e:
        exc = e

    return result, exc, handler


# ─────────────────────────────────────────────────────────────────────────────
# Test cases — 6 failure scenarios
# ─────────────────────────────────────────────────────────────────────────────

async def test_scenario_1_network_timeout_returns_UNKNOWN() -> None:
    """Scenario 1: Network timeout (ConnectTimeout + ReadTimeout) → UNKNOWN.

    Verifies both connect-level and read-level timeouts are caught and
    degraded gracefully. This maps to '系统不崩溃，返回用户友好错误'.
    """
    text = "下周三前完成 API 设计"

    # 1a: ConnectTimeout
    result, exc, handler = await _run_with_fault("connect_timeout", text=text)
    _assert_no_exception(result, exc, "ConnectTimeout")
    _assert_degraded_response(result, text, "ConnectTimeout")
    _assert_log_contains(handler, "[minimax/failure/")

    # 1b: ReadTimeout
    result, exc, handler = await _run_with_fault("read_timeout", text=text)
    _assert_no_exception(result, exc, "ReadTimeout")
    _assert_degraded_response(result, text, "ReadTimeout")
    _assert_log_contains(handler, "[minimax/failure/")


async def test_scenario_2_server_5xx_returns_UNKNOWN() -> None:
    """Scenario 2: Server 5xx errors (500, 502, 503) → UNKNOWN.

    Verifies that internal server errors and gateway errors from MiniMax
    do not crash the system and produce a safe degraded response.
    """
    text = "帮我创建一个新任务"

    for status in (500, 502, 503):
        result, exc, handler = await _run_with_fault("http_error", text=text, status_code=status)
        _assert_no_exception(result, exc, f"HTTP {status}")
        _assert_degraded_response(result, text, f"HTTP {status}")
        _assert_log_contains(handler, f"[minimax/failure/http_{status}]")


async def test_scenario_3_api_key_invalid_returns_UNKNOWN() -> None:
    """Scenario 3: API Key invalid (401 / 403) → UNKNOWN.

    Verifies authentication failures are caught and logged with the
    correct auth error markers, returning safe UNKNOWN intent.
    """
    text = "查看我的任务列表"

    for status in (401, 403):
        result, exc, handler = await _run_with_fault("http_error", text=text, status_code=status)
        _assert_no_exception(result, exc, f"HTTP {status}")
        _assert_degraded_response(result, text, f"HTTP {status}")
        _assert_log_contains(handler, f"[minimax/failure/http_{status}]")


async def test_scenario_4_rate_limit_429_returns_UNKNOWN() -> None:
    """Scenario 4: Rate limiting (429 + Retry-After header) → UNKNOWN.

    Verifies that HTTP 429 responses with Retry-After header are handled
    gracefully without crashing. The Retry-After header is included to
    test the full real-world response shape.
    """
    text = "列出所有未完成的任务"
    headers = {"Retry-After": "60"}

    result, exc, handler = await _run_with_fault(
        "http_error", text=text, status_code=429, headers=headers
    )
    _assert_no_exception(result, exc, "HTTP 429")
    _assert_degraded_response(result, text, "HTTP 429")
    _assert_log_contains(handler, "[minimax/failure/http_429]")

    # Verify the result is safe for WeChat "服务暂时不可用" reply
    assert result.action == IntentAction.UNKNOWN
    assert result.confidence == 0.0


async def test_scenario_5_non_json_response_returns_UNKNOWN() -> None:
    """Scenario 5: Response format anomaly (non-JSON body) → UNKNOWN.

    Verifies that when MiniMax returns a 200 response with invalid JSON
    content (e.g., HTML error page, truncated response, internal server
    error body), the parser catches the decode failure and returns UNKNOWN.
    """
    text = "创建任务：完成文档"

    result, exc, handler = await _run_with_fault("invalid_json", text=text)
    _assert_no_exception(result, exc, "Non-JSON")
    _assert_degraded_response(result, text, "Non-JSON")
    _assert_log_contains(handler, "[minimax/failure/")


async def test_scenario_6_missing_response_fields_returns_UNKNOWN() -> None:
    """Scenario 6: Response field missing (schema validation failure) → UNKNOWN.

    Verifies two sub-cases:
    6a. MiniMax returns valid JSON but inner content lacks required fields
        (e.g., partial response, schema change on provider side).
    6b. MiniMax returns empty choices array (edge case in production).

    Both must produce UNKNOWN intent, never crash.
    Note: 6a is handled silently by IntentParser (Pydantic returns defaults),
          6b raises APIError → IntentParsingError → caught by analyze_intent.
    """
    text = "下周三前完成 API 设计"

    # 6a: Valid JSON outer structure, but inner content missing required fields
    result, exc, handler = await _run_with_fault("missing_fields", text=text)
    _assert_no_exception(result, exc, "Missing fields")
    _assert_UNKNOWN(result, "Missing fields")
    assert result.raw_text == text
    # No log marker expected — IntentParser._parse_response handles this case
    # silently via Pydantic defaults (action=UNKNOWN) and validation fallback.

    # 6b: Empty choices array from MiniMax
    result, exc, handler = await _run_with_fault("empty_choices", text=text)
    _assert_no_exception(result, exc, "Empty choices")
    _assert_degraded_response(result, text, "Empty choices")
    _assert_log_contains(handler, "[minimax/failure/")
