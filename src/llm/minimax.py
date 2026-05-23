"""MiniMax LLM provider using httpx async client.

Implements the LLMProvider protocol from ADR-001 for the MiniMax model.
Uses httpx async client with 30s timeout per request.
"""
from __future__ import annotations

import json
import logging
import os
from abc import abstractmethod
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from src.domain.intent import IntentData

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Protocol (Trait) — mirrors the architecture doc
# ─────────────────────────────────────────────────────────────────────────────


class LLMProvider:
    """Abstract LLM provider protocol.

    Concrete implementations must provide `complete` and `embed` methods.
    Used by AIBrain for model-agnostic LLM access.
    """

    @abstractmethod
    async def complete(self, prompt: str, system: str | None = None) -> str:
        """Send a completion request to the LLM.

        Args:
            prompt: The user prompt text.
            system: Optional system prompt.

        Returns:
            The raw response string from the LLM.

        Raises:
            LLMError: On network, auth, or API errors.
        """
        ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate an embedding vector for the given text.

        Args:
            text: Input text to embed.

        Returns:
            List of float embedding dimensions.

        Raises:
            LLMError: On network, auth, or API errors.
        """
        ...


# ─────────────────────────────────────────────────────────────────────────────
# Errors
# ─────────────────────────────────────────────────────────────────────────────


class LLMError(Exception):
    """Base exception for LLM provider errors."""

    pass


class AuthenticationError(LLMError):
    """Raised when the API key is invalid or missing."""

    pass


class RateLimitError(LLMError):
    """Raised when the API rate limit is exceeded."""

    pass


class APIError(LLMError):
    """Raised when the API returns a non-success status code."""

    def __init__(self, message: str, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


# ─────────────────────────────────────────────────────────────────────────────
# MiniMax Provider
# ─────────────────────────────────────────────────────────────────────────────


class MiniMaxProvider(LLMProvider):
    """MiniMax LLM provider using the MiniMax-M2.7 / MiniMax-Text-01 model.

    API Reference: https://www.minimaxi.com/docs/api/
    Endpoint:      https://api.minimax.chat/v1/text/chatcompletion_v2

    Args:
        api_key: MiniMax API key. Falls back to ART_MINIMAX_API_KEY env var.
        model:   Model name. Defaults to MiniMax-Text-01.
        timeout: Request timeout in seconds. Defaults to 30.
    """

    DEFAULT_BASE_URL = "https://api.minimax.chat/v1"
    DEFAULT_MODEL = "MiniMax-Text-01"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        resolved_key = api_key or os.environ.get("ART_MINIMAX_API_KEY", "")
        if not resolved_key:
            # Also check the legacy MINIMAX_API_KEY without prefix
            resolved_key = os.environ.get("MINIMAX_API_KEY", "")

        if not resolved_key:
            raise AuthenticationError(
                "MiniMax API key not set. "
                "Set ART_MINIMAX_API_KEY or MINIMAX_API_KEY environment variable."
            )

        self._api_key = resolved_key
        self._model = model or self.DEFAULT_MODEL
        self._timeout = timeout
        self._base_url = self.DEFAULT_BASE_URL
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazily create and return the shared httpx client."""
        if self._client is None or self._client.is_closed:
            self._client = _build_client(api_key=self._api_key, timeout=self._timeout)
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def complete(self, prompt: str, system: str | None = None) -> str:
        """Send a chat completion request to MiniMax.

        Args:
            prompt: User message.
            system: Optional system prompt.

        Returns:
            The content of the first response message.

        Raises:
            AuthenticationError: On 401/403.
            RateLimitError:      On 429.
            APIError:            On other non-success HTTP status codes.
            LLMError:            On network/timeout errors.
        """
        client = await self._get_client()

        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
        }

        try:
            response = await client.post("/text/chatcompletion_v2", json=payload)
        except httpx.TimeoutException as e:
            raise LLMError(f"MiniMax request timed out after {self._timeout}s") from e
        except httpx.HTTPError as e:
            # Re-raise httpx-level errors as LLMError (covers network/connect issues
            # not tied to an HTTP response). For HTTP status-code errors the code
            # below raises the appropriate typed exception (AuthenticationError,
            # RateLimitError, APIError) so callers can distinguish 5xx from 401/403.
            raise LLMError(f"MiniMax HTTP error: {e}") from e

        if response.status_code == 401:
            raise AuthenticationError(
                f"MiniMax authentication failed (status {response.status_code}). "
                "Check your API key."
            )
        if response.status_code == 403:
            raise APIError(
                f"MiniMax API forbidden (status {response.status_code}).",
                status_code=response.status_code,
            )
        if response.status_code == 429:
            raise RateLimitError(
                f"MiniMax rate limit exceeded (status {response.status_code})."
            )
        if not response.is_success:
            raise APIError(
                f"MiniMax API error: {response.text}",
                status_code=response.status_code,
            )

        try:
            data = response.json()
        except json.JSONDecodeError as e:
            raise LLMError(f"MiniMax response was not valid JSON: {e}") from e
        choices = data.get("choices", [])
        if not choices:
            raise APIError(f"MiniMax returned no choices: {data}")

        # First choice's first message content
        message = choices[0].get("message", {})
        content = message.get("content", "")
        return content

    async def embed(self, text: str) -> list[float]:
        """Generate a text embedding via MiniMax embedding API.

        Note: MiniMax embedding endpoint is separate from chat completion.
        This uses the MiniMax embedding v1 API.

        Args:
            text: Input text.

        Returns:
            List of float embedding dimensions.

        Raises:
            AuthenticationError: On 401/403.
            RateLimitError:      On 429.
            APIError:            On other non-success status codes.
            LLMError:            On network/timeout errors.
        """
        client = await self._get_client()

        payload: dict[str, Any] = {
            "model": "embedding-01",
            "texts": [text],
        }

        try:
            response = await client.post("/text/embeddings", json=payload)
        except httpx.TimeoutException as e:
            raise LLMError(f"MiniMax embedding request timed out after {self._timeout}s") from e
        except httpx.HTTPError as e:
            raise LLMError(f"MiniMax embedding HTTP error: {e}") from e

        if response.status_code == 401 or response.status_code == 403:
            raise AuthenticationError(
                f"MiniMax embedding auth failed (status {response.status_code})."
            )
        if response.status_code == 429:
            raise RateLimitError(
                f"MiniMax embedding rate limit exceeded (status {response.status_code})."
            )
        if not response.is_success:
            raise APIError(
                f"MiniMax embedding API error: {response.text}",
                status_code=response.status_code,
            )

        try:
            data = response.json()
        except json.JSONDecodeError as e:
            raise LLMError(f"MiniMax embedding response was not valid JSON: {e}") from e
        embeddings = data.get("data", [])
        if not embeddings:
            raise APIError(f"MiniMax returned no embeddings: {data}")

        return embeddings[0].get("embedding", [])


# ─────────────────────────────────────────────────────────────────────────────
# Module-level client factory (exposed for test injection via monkeypatch)
# ─────────────────────────────────────────────────────────────────────────────


def _build_client(api_key: str, timeout: float = 30.0) -> httpx.AsyncClient:
    """Build the shared httpx AsyncClient for MiniMax API calls.

    Extracted as a module-level function so fault-injection tests can
    replace it via ``monkeypatch.setattr(minimax, "_build_client", ...)``.

    Args:
        api_key: MiniMax API key for Bearer auth.
        timeout: Request timeout in seconds.

    Returns:
        Configured ``httpx.AsyncClient`` instance.
    """
    return httpx.AsyncClient(
        base_url=MiniMaxProvider.DEFAULT_BASE_URL,
        timeout=httpx.Timeout(timeout),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Module-level factory
# ─────────────────────────────────────────────────────────────────────────────


async def get_minimax_provider() -> MiniMaxProvider:
    """Factory function that reads config and returns a MiniMaxProvider instance.

    Returns:
        Configured MiniMaxProvider.
    """
    # Import here to avoid circular imports
    from src.utils.config import get_config

    config = get_config()
    minimax_cfg = config.minimax

    if minimax_cfg is None:
        # No explicit config — rely on env vars
        return MiniMaxProvider()

    return MiniMaxProvider(
        api_key=minimax_cfg.api_key or None,
        model=minimax_cfg.model or MiniMaxProvider.DEFAULT_MODEL,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Top-level intent analysis entry point (used by fault-tolerance tests)
# ─────────────────────────────────────────────────────────────────────────────


async def analyze_intent(
    text: str,
    *,
    provider: MiniMaxProvider | None = None,
) -> IntentData:
    """Parse a user message into structured IntentData via MiniMax.

    This is the high-level entry point used by the WeChat adapter and other
    consumers. It wraps the full pipeline:
        MiniMaxProvider.complete() → parse JSON → IntentData

    Fault-tolerance behaviour (per Sprint 2 acceptance criteria):
        All failures (transport timeout, HTTP 5xx, 401/403, rate-limit, …
        invalid JSON) are caught, logged with a ``[minimax/failure/<scenario>]``
        marker, and return ``IntentData(action=IntentAction.UNKNOWN)`` as a
        degraded-but-safe result. No exception propagates to callers.

    Args:
        text: The raw user message to analyse.
        provider: Optional MiniMaxProvider instance. If not provided, a new one
            is created using the configured API key. Accepting a provider
            enables dependency injection for unit testing.

    Returns:
        IntentData — validated structured intent, or ``IntentData(action=UNKNOWN)``
        on any failure.
    """
    # Import here to avoid circular import at module load time
    from src.domain.intent import IntentAction, IntentData
    from src.llm.intent_parser import IntentParser, IntentParsingError

    logger2 = logging.getLogger("src.llm.minimax")

    try:
        if provider is None:
            provider = MiniMaxProvider()
        parser = IntentParser(provider=provider)
        return await parser.parse(text)
    except IntentParsingError as exc:
        # IntentParser carries a specific failure marker from the underlying LLM error
        marker = getattr(exc, "failure_marker", None) or "unknown"
        logger2.exception(f"[minimax/failure/{marker}] Intent parsing failed")
        return IntentData(action=IntentAction.UNKNOWN, confidence=0.0, raw_text=text)
    except AuthenticationError:
        logger2.exception("[minimax/failure/http_401] API key invalid")
        return IntentData(action=IntentAction.UNKNOWN, confidence=0.0, raw_text=text)
    except RateLimitError:
        logger2.exception("[minimax/failure/http_429] Rate limit exceeded")
        return IntentData(action=IntentAction.UNKNOWN, confidence=0.0, raw_text=text)
    except APIError as exc:
        if exc.status_code == 500:
            logger2.exception("[minimax/failure/http_500] MiniMax server error")
        elif exc.status_code in (502, 503):
            logger2.exception(f"[minimax/failure/http_{exc.status_code}] Gateway error")
        else:
            logger2.exception(f"[minimax/failure/http_{exc.status_code}] API error")
        return IntentData(action=IntentAction.UNKNOWN, confidence=0.0, raw_text=text)
    except LLMError:
        # Covers network/timeout errors raised as LLMError subclasses
        logger2.exception("[minimax/failure/llm_error] LLM error")
        return IntentData(action=IntentAction.UNKNOWN, confidence=0.0, raw_text=text)
    except Exception:
        # Defensive: any unexpected error must not propagate
        logger2.exception("[minimax/failure/unknown] Unexpected error in analyze_intent")
        return IntentData(action=IntentAction.UNKNOWN, confidence=0.0, raw_text=text)
