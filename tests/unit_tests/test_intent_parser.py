"""Unit tests for the MiniMax intent parser.

These tests use mocking to avoid real API calls.
Mock tests must satisfy P99 latency < 5s per the acceptance criteria.

Fixtures:
    tests/fixtures/intent_golden_dataset.json — golden dataset for intent parsing.
"""
from __future__ import annotations

import asyncio
import json
import statistics
import time
from importlib import resources
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.intent import IntentAction, IntentData, TaskPriority
from src.llm.intent_parser import IntentParser, IntentParsingError
from src.llm.minimax import (
    APIError,
    AuthenticationError,
    LLMError,
    MiniMaxProvider,
    RateLimitError,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def golden_dataset() -> list[dict[str, Any]]:
    """Load the golden dataset for intent parsing tests."""
    fixtures_path = Path(__file__).parent.parent / "fixtures" / "intent_golden_dataset.json"
    with open(fixtures_path) as f:
        data = json.load(f)
    return data["cases"]


@pytest.fixture
def mock_provider() -> MiniMaxProvider:
    """Create a mock MiniMaxProvider with a mocked complete method."""
    provider = MiniMaxProvider(api_key="test-key")
    # Replace complete with an async mock
    provider.complete = AsyncMock()  # type: ignore[assignment]
    return provider


# ─────────────────────────────────────────────────────────────────────────────
# Tests — IntentParser unit tests with mocked LLM
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_parse_create_task(mock_provider: MiniMaxProvider, golden_dataset: list[dict[str, Any]]) -> None:
    """Test that a 'create task' message is correctly parsed."""
    case = next(c for c in golden_dataset if c["id"] == "case_001")

    # Build expected JSON response
    expected_response = json.dumps(case["expected"], ensure_ascii=False)
    mock_provider.complete = AsyncMock(return_value=expected_response)  # type: ignore[assignment]

    parser = IntentParser(provider=mock_provider)
    result = await parser.parse(case["input"])

    assert result.action == IntentAction.CREATE_TASK
    assert result.estimated_hours == 4.0
    assert result.suggested_priority.value == "high"
    assert result.raw_text == case["input"]


@pytest.mark.asyncio
async def test_parse_list_tasks(mock_provider: MiniMaxProvider, golden_dataset: list[dict[str, Any]]) -> None:
    """Test that a 'list tasks' message is correctly parsed."""
    case = next(c for c in golden_dataset if c["id"] == "case_004")

    expected_response = json.dumps(case["expected"], ensure_ascii=False)
    mock_provider.complete = AsyncMock(return_value=expected_response)  # type: ignore[assignment]

    parser = IntentParser(provider=mock_provider)
    result = await parser.parse(case["input"])

    assert result.action == IntentAction.LIST_TASKS
    assert result.confidence == 0.95


@pytest.mark.asyncio
async def test_parse_assign_task(mock_provider: MiniMaxProvider, golden_dataset: list[dict[str, Any]]) -> None:
    """Test that an 'assign task' message is correctly parsed."""
    case = next(c for c in golden_dataset if c["id"] == "case_005")

    expected_response = json.dumps(case["expected"], ensure_ascii=False)
    mock_provider.complete = AsyncMock(return_value=expected_response)  # type: ignore[assignment]

    parser = IntentParser(provider=mock_provider)
    result = await parser.parse(case["input"])

    assert result.action == IntentAction.ASSIGN_TASK


@pytest.mark.asyncio
async def test_parse_greeting_returns_unknown(mock_provider: MiniMaxProvider, golden_dataset: list[dict[str, Any]]) -> None:
    """Test that a greeting is classified as 'unknown' intent."""
    case = next(c for c in golden_dataset if c["id"] == "case_006")

    expected_response = json.dumps(case["expected"], ensure_ascii=False)
    mock_provider.complete = AsyncMock(return_value=expected_response)  # type: ignore[assignment]

    parser = IntentParser(provider=mock_provider)
    result = await parser.parse(case["input"])

    assert result.action == IntentAction.UNKNOWN
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_parse_urgent_message(mock_provider: MiniMaxProvider, golden_dataset: list[dict[str, Any]]) -> None:
    """Test that an urgent message gets 'urgent' priority."""
    case = next(c for c in golden_dataset if c["id"] == "case_003")

    expected_response = json.dumps(case["expected"], ensure_ascii=False)
    mock_provider.complete = AsyncMock(return_value=expected_response)  # type: ignore[assignment]

    parser = IntentParser(provider=mock_provider)
    result = await parser.parse(case["input"])

    assert result.action == IntentAction.CREATE_TASK
    assert result.suggested_priority.value == "urgent"
    assert result.suggested_due_date is not None


@pytest.mark.asyncio
async def test_parse_empty_message_returns_unknown(mock_provider: MiniMaxProvider) -> None:
    """Test that an empty/whitespace message returns unknown intent without calling LLM."""
    parser = IntentParser(provider=mock_provider)

    result = await parser.parse("")

    assert result.action == IntentAction.UNKNOWN
    assert result.confidence == 0.0
    mock_provider.complete.assert_not_called()


@pytest.mark.asyncio
async def test_parse_llm_returns_invalid_json(mock_provider: MiniMaxProvider) -> None:
    """Test that a non-JSON LLM response falls back to unknown intent."""
    mock_provider.complete = AsyncMock(return_value="This is not JSON { broken")  # type: ignore[assignment]

    parser = IntentParser(provider=mock_provider)
    result = await parser.parse("some task")

    assert result.action == IntentAction.UNKNOWN
    assert result.confidence == 0.0


@pytest.mark.asyncio
async def test_parse_llm_returns_plain_json_without_markdown(mock_provider: MiniMaxProvider) -> None:
    """Test parsing when LLM returns raw JSON without markdown fences."""
    raw_json = json.dumps({
        "action": "create_task",
        "estimated_hours": 2.0,
        "suggested_priority": "medium",
        "suggested_due_date": "2026-05-30",
        "confidence": 0.85,
        "raw_text": "测试消息",
    })
    mock_provider.complete = AsyncMock(return_value=raw_json)  # type: ignore[assignment]

    parser = IntentParser(provider=mock_provider)
    result = await parser.parse("测试消息")

    assert result.action == IntentAction.CREATE_TASK
    assert result.estimated_hours == 2.0


@pytest.mark.asyncio
async def test_parse_llm_returns_markdown_json_block(mock_provider: MiniMaxProvider) -> None:
    """Test parsing when LLM returns JSON inside a markdown code block."""
    raw_response = '''
    ```json
    {
      "action": "create_task",
      "estimated_hours": 3.0,
      "suggested_priority": "high",
      "suggested_due_date": "2026-06-01",
      "confidence": 0.88,
      "raw_text": "完成系统设计"
    }
    ```
    '''
    mock_provider.complete = AsyncMock(return_value=raw_response)  # type: ignore[assignment]

    parser = IntentParser(provider=mock_provider)
    result = await parser.parse("完成系统设计")

    assert result.action == IntentAction.CREATE_TASK
    assert result.estimated_hours == 3.0
    assert result.suggested_priority.value == "high"


@pytest.mark.asyncio
async def test_parse_raises_intent_parsing_error_on_llm_failure(mock_provider: MiniMaxProvider) -> None:
    """Test that LLM errors are wrapped as IntentParsingError."""
    mock_provider.complete = AsyncMock(side_effect=AuthenticationError("Invalid key"))  # type: ignore[assignment]

    parser = IntentParser(provider=mock_provider)

    with pytest.raises(IntentParsingError) as exc_info:
        await parser.parse("create a task")

    assert isinstance(exc_info.value.__cause__, AuthenticationError)


# ─────────────────────────────────────────────────────────────────────────────
# Tests — MiniMaxProvider error handling
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_provider_raises_auth_error_without_key() -> None:
    """Test that MiniMaxProvider raises AuthenticationError without API key."""
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(AuthenticationError):
            MiniMaxProvider(api_key="")


@pytest.mark.asyncio
async def test_provider_complete_returns_content() -> None:
    """Test that MiniMaxProvider.complete returns the message content."""
    provider = MiniMaxProvider(api_key="test-key")

    mock_response = {
        "choices": [
            {"message": {"content": "Hello from MiniMax"}}
        ]
    }

    with patch.object(provider, "_get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_response_obj = MagicMock()
        mock_response_obj.is_success = True
        mock_response_obj.status_code = 200
        mock_response_obj.json.return_value = mock_response
        mock_response_obj.text = ""
        mock_client.post.return_value = mock_response_obj
        mock_get_client.return_value = mock_client

        result = await provider.complete("Say hello")

        assert result == "Hello from MiniMax"
        mock_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_provider_complete_raises_auth_error_on_401() -> None:
    """Test that a 401 response raises AuthenticationError."""
    provider = MiniMaxProvider(api_key="bad-key")

    with patch.object(provider, "_get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_response_obj = AsyncMock()
        mock_response_obj.is_success = False
        mock_response_obj.status_code = 401
        mock_response_obj.text = "Unauthorized"
        mock_client.post.return_value = mock_response_obj
        mock_get_client.return_value = mock_client

        with pytest.raises(AuthenticationError):
            await provider.complete("test")


@pytest.mark.asyncio
async def test_provider_complete_raises_rate_limit_on_429() -> None:
    """Test that a 429 response raises RateLimitError."""
    provider = MiniMaxProvider(api_key="test-key")

    with patch.object(provider, "_get_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_response_obj = AsyncMock()
        mock_response_obj.is_success = False
        mock_response_obj.status_code = 429
        mock_response_obj.text = "Rate limit exceeded"
        mock_client.post.return_value = mock_response_obj
        mock_get_client.return_value = mock_client

        with pytest.raises(RateLimitError):
            await provider.complete("test")


# ─────────────────────────────────────────────────────────────────────────────
# Tests — P99 latency requirement (< 5s)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_p99_latency_under_5_seconds(mock_provider: MiniMaxProvider, golden_dataset: list[dict[str, Any]]) -> None:
    """Mock test P99 latency must be < 5s per acceptance criteria.

    Runs all golden dataset cases and measures end-to-end parse latency.
    """
    latencies: list[float] = []

    for case in golden_dataset:
        expected_response = json.dumps(case["expected"], ensure_ascii=False)
        mock_provider.complete = AsyncMock(return_value=expected_response)  # type: ignore[assignment]

        parser = IntentParser(provider=mock_provider)

        start = time.perf_counter()
        result = await parser.parse(case["input"])
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)

        # Sanity check: result is valid IntentData
        assert isinstance(result, IntentData)
        assert result.action != IntentAction.UNKNOWN or case["id"] in ("case_006", "case_009")

    p99 = statistics.quantiles(latencies, n=100)[98]
    mean = statistics.mean(latencies)
    max_latency = max(latencies)

    assert p99 < 5.0, (
        f"P99 latency {p99:.3f}s exceeds 5s threshold. "
        f"Mean: {mean:.3f}s, Max: {max_latency:.3f}s"
    )


@pytest.mark.asyncio
async def test_all_golden_cases_parse_correctly(mock_provider: MiniMaxProvider, golden_dataset: list[dict[str, Any]]) -> None:
    """Test that every golden dataset case is parsed correctly with mocked LLM."""
    failures: list[str] = []

    for case in golden_dataset:
        expected = case["expected"]
        expected_response = json.dumps(expected, ensure_ascii=False)
        mock_provider.complete = AsyncMock(return_value=expected_response)  # type: ignore[assignment]

        parser = IntentParser(provider=mock_provider)
        result = await parser.parse(case["input"])

        # Compare key fields
        if result.action.value != expected["action"]:
            failures.append(
                f"{case['id']}: action={result.action.value}, expected={expected['action']}"
            )
        if result.estimated_hours != expected["estimated_hours"]:
            failures.append(
                f"{case['id']}: estimated_hours={result.estimated_hours}, "
                f"expected={expected['estimated_hours']}"
            )
        if (result.suggested_priority.value if result.suggested_priority else None) != expected["suggested_priority"]:
            failures.append(
                f"{case['id']}: suggested_priority={result.suggested_priority}, "
                f"expected={expected['suggested_priority']}"
            )
        if result.confidence != expected["confidence"]:
            failures.append(
                f"{case['id']}: confidence={result.confidence}, expected={expected['confidence']}"
            )

    assert not failures, "Golden dataset failures:\n" + "\n".join(failures)


# ─────────────────────────────────────────────────────────────────────────────
# Tests — IntentData schema validation
# ─────────────────────────────────────────────────────────────────────────────


def test_intent_data_accepts_valid_model() -> None:
    """Test that IntentData.model_validate accepts a valid intent dict."""
    data = {
        "action": "create_task",
        "estimated_hours": 2.5,
        "suggested_priority": "high",
        "suggested_due_date": "2026-06-01",
        "confidence": 0.92,
        "raw_text": "下周三前完成 API 设计",
    }
    intent = IntentData.model_validate(data)

    assert intent.action == IntentAction.CREATE_TASK
    assert intent.estimated_hours == 2.5
    assert intent.suggested_priority == TaskPriority.HIGH
    assert intent.suggested_due_date.year == 2026


def test_intent_data_rejects_invalid_priority() -> None:
    """Test that IntentData rejects an invalid priority value."""
    data = {
        "action": "create_task",
        "suggested_priority": "invalid_priority",
    }
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        IntentData.model_validate(data)


def test_intent_data_estimated_hours_bounds() -> None:
    """Test that estimated_hours is bounded to [0, 168]."""
    from pydantic import ValidationError
    # Over upper bound
    with pytest.raises(ValidationError):
        IntentData.model_validate({"estimated_hours": 200})
    # Negative
    with pytest.raises(ValidationError):
        IntentData.model_validate({"estimated_hours": -1})


def test_intent_data_confidence_bounds() -> None:
    """Test that confidence must be in [0.0, 1.0]."""
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        IntentData.model_validate({"confidence": 1.5})
    with pytest.raises(ValidationError):
        IntentData.model_validate({"confidence": -0.1})
