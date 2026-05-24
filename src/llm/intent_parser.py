"""Intent parsing service using MiniMax LLM.

Translates natural language user messages into structured IntentData JSON
for task management.

Prompt template follows ADR-001: given user message text,
returns structured JSON (intent type + entities).
"""
from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

from src.domain.intent import IntentAction, IntentData, TaskPriority
from src.llm.base import LLMError
from src.llm.glm import GLMProvider, get_glm_provider

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Prompt Template
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an intent parser for a personal task management AI agent.
Given a user message in Chinese or English, extract structured task information.

Return ONLY valid JSON with these fields:
{
  "action": "create_task" | "update_task" | "assign_task" | "complete_task" | "delete_task" | "list_tasks" | "help" | "unknown",
  "estimated_hours": number | null,
  "suggested_priority": "low" | "medium" | "high" | "urgent" | null,
  "suggested_due_date": "YYYY-MM-DD" | null,
  "confidence": number between 0.0 and 1.0,
  "raw_text": "the original user message"
}

Rules:
- estimated_hours: 0.5 increments, max 168 (1 week). null if not mentioned.
- suggested_priority: "urgent" only if deadline is within 24h or explicitly urgent.
- suggested_due_date: ISO date string (YYYY-MM-DD), null if not mentioned.
- confidence: how confident you are in the action classification (0.0-1.0).
- raw_text: always copy the original user message exactly.
- If the message is not about a task (e.g., just greeting), set action to "unknown".
"""

USER_PROMPT_TEMPLATE = """解析以下用户消息，提取结构化任务信息：

{user_message}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Intent Parser
# ─────────────────────────────────────────────────────────────────────────────


class IntentParsingError(Exception):
    """Raised when intent parsing fails at the service layer."""

    def __init__(self, message: str, *, failure_marker: str | None = None) -> None:
        super().__init__(message)
        self.failure_marker = failure_marker


class IntentParser:
    """Parses natural language messages into structured IntentData.

    Uses GLM LLM to analyze user messages and extract intent entities.
    The result is a validated IntentData object.

    Usage:
        parser = IntentParser(provider)
        intent = await parser.parse("下周三前完成 API 设计")
    """

    def __init__(self, provider: GLMProvider | None = None) -> None:
        """Initialize the intent parser.

        Args:
            provider: GLM provider instance. If None, created from config.
        """
        self._provider = provider

    @property
    def provider(self) -> GLMProvider:
        """Return the provider, which must be set at construction time.

        This property exists so callers can access the provider for lifecycle
        management (e.g., closing the HTTP client). Always access via this
        property rather than _provider directly.
        """
        if self._provider is None:
            raise RuntimeError(
                "IntentParser: no MiniMax provider set. "
                "Pass provider=... to the constructor, or use get_intent_parser()."
            )
        return self._provider

    async def parse(self, user_message: str) -> IntentData:
        """Parse a user message into structured IntentData.

        Args:
            user_message: The raw user input text.

        Returns:
            Validated IntentData object.

        Raises:
            IntentParsingError: If the LLM call fails or response is unparseable.
        """
        if not user_message or not user_message.strip():
            return IntentData(
                action=IntentAction.UNKNOWN,
                confidence=0.0,
                raw_text=user_message,
            )

        try:
            raw_response = await self.provider.complete(
                prompt=USER_PROMPT_TEMPLATE.format(user_message=user_message.strip()),
                system=SYSTEM_PROMPT,
            )
        except LLMError as e:
            marker = self._failure_marker_for(e)
            raise IntentParsingError(f"LLM request failed: {e}", failure_marker=marker) from e

        return self._parse_response(raw_response, user_message)

    def _failure_marker_for(self, exc: Exception) -> str:
        """Determine log marker from an LLM error or its cause chain."""
        import json

        from src.llm.base import APIError, AuthenticationError, RateLimitError
        import httpx

        if isinstance(exc, RateLimitError):
            return "http_429"
        if isinstance(exc, AuthenticationError):
            return "http_401"
        if isinstance(exc, APIError) and exc.status_code:
            return f"http_{exc.status_code}"
        # Timeout errors → specific markers
        if isinstance(exc, httpx.TimeoutException):
            return "connect_timeout" if "connect" in str(exc).lower() else "read_timeout"
        # JSON decode errors → invalid_json marker
        if isinstance(exc, json.JSONDecodeError):
            return "invalid_json"
        # httpx DecodingError wraps json.JSONDecodeError from response.json() failures
        # (renamed from DecodeError in httpx >= 0.28)
        if hasattr(httpx, "DecodingError") and isinstance(exc, httpx.DecodingError):
            return "invalid_json"
        if hasattr(httpx, "DecodeError") and isinstance(exc, httpx.DecodeError):  # type: ignore[attr-defined]
            return "invalid_json"
        # Check nested cause — complete() wraps httpx errors into LLMError
        if exc.__cause__ is not None and isinstance(exc.__cause__, Exception):
            return self._failure_marker_for(exc.__cause__)
        return "llm_error"

    def _parse_response(self, raw_response: str, original_message: str) -> IntentData:
        """Parse the LLM raw text response into IntentData.

        The LLM should return a JSON block. We extract it and validate it
        against the IntentData schema.

        Args:
            raw_response: Raw text from the LLM.
            original_message: The original user message (used for fallback).

        Returns:
            Validated IntentData.

        Raises:
            IntentParsingError: If the response cannot be parsed as JSON
                                or fails schema validation.
        """
        # Try to extract a JSON code block first
        json_text = self._extract_json(raw_response)
        if json_text is None:
            logger.warning(
                "Could not extract JSON from LLM response: %r",
                raw_response[:200],
            )
            return IntentData(
                action=IntentAction.UNKNOWN,
                confidence=0.0,
                raw_text=original_message,
            )

        try:
            parsed = json.loads(json_text)
        except json.JSONDecodeError as e:
            logger.warning("Invalid JSON from LLM: %s. Raw: %r", e, json_text[:200])
            return IntentData(
                action=IntentAction.UNKNOWN,
                confidence=0.0,
                raw_text=original_message,
            )

        # Merge raw_text with original if not set
        if not parsed.get("raw_text"):
            parsed["raw_text"] = original_message

        try:
            return IntentData.model_validate(parsed)
        except Exception as e:
            logger.warning(
                "IntentData validation failed: %s. JSON: %r",
                e,
                json_text[:200],
            )
            # Return unknown intent rather than crashing
            return IntentData(
                action=IntentAction.UNKNOWN,
                confidence=0.0,
                raw_text=original_message,
            )

    @staticmethod
    def _extract_json(text: str) -> str | None:
        """Extract JSON from an LLM response that may contain markdown code fences.

        Handles:
          ```json
          {...}
          ```
        or raw {...} text.

        Args:
            text: Raw LLM output text.

        Returns:
            The JSON string if found, or None.
        """
        text = text.strip()

        # Try markdown code block first
        match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if match:
            return match.group(1).strip()

        # Try raw opening brace
        if text.startswith("{"):
            # Find the matching closing brace
            depth = 0
            for i, ch in enumerate(text):
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return text[: i + 1]
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Async factory (preferred — use this in async contexts)
# ─────────────────────────────────────────────────────────────────────────────


async def get_intent_parser(provider: GLMProvider | None = None) -> IntentParser:
    """Factory function to get an IntentParser.

    Args:
        provider: Optional pre-configured GLM provider.

    Returns:
        IntentParser instance.
    """
    if provider is None:
        provider = await get_glm_provider()
    return IntentParser(provider=provider)
