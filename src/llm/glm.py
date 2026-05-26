"""GLM LLM provider using httpx async client.

Implements the LLMProvider protocol from ADR-001 for the GLM model.
Uses httpx async client with 30s timeout per request.
"""
from __future__ import annotations

import json
import logging
import os
from typing import TYPE_CHECKING, Any

import httpx

from src.llm.base import (
    APIError,
    AuthenticationError,
    LLMError,
    LLMProvider,
    RateLimitError,
)

if TYPE_CHECKING:
    from src.domain.intent import IntentData

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# GLM Provider
# ─────────────────────────────────────────────────────────────────────────────


class GLMProvider(LLMProvider):
    """GLM LLM provider using the GLM-4.6-Flash model.

    API Reference: https://open.bigmodel.cn/api/paas/v4
    Endpoint:      https://open.bigmodel.cn/api/paas/v4

    Args:
        api_key: GLM API key. Falls back to ART_GLM_API_KEY env var.
        model:   Model name. Defaults to glm-4.6-flash.
        timeout: Request timeout in seconds. Defaults to 30.
    """

    DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
    DEFAULT_MODEL = "glm-4.6-flash"

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        resolved_key = api_key or os.environ.get("ART_GLM_API_KEY", "")
        if not resolved_key:
            # Also check the legacy GLM_API_KEY without prefix
            resolved_key = os.environ.get("GLM_API_KEY", "")

        if not resolved_key:
            raise AuthenticationError(
                "GLM API key not set. "
                "Set ART_GLM_API_KEY or GLM_API_KEY environment variable."
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
        """Send a chat completion request to GLM.

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
            "temperature": 0.7,
            "max_tokens": 4000,
        }

        try:
            response = await client.post("/chat/completions", json=payload)
        except httpx.TimeoutException as e:
            raise LLMError(f"GLM request timed out after {self._timeout}s") from e
        except httpx.HTTPError as e:
            # Re-raise httpx-level errors as LLMError (covers network/connect issues
            # not tied to an HTTP response). For HTTP status-code errors the code
            # below raises the appropriate typed exception (AuthenticationError,
            # RateLimitError, APIError) so callers can distinguish 5xx from 401/403.
            raise LLMError(f"GLM HTTP error: {e}") from e

        if response.status_code == 401:
            raise AuthenticationError(
                f"GLM authentication failed (status {response.status_code}). "
                "Check your API key."
            )
        if response.status_code == 403:
            raise APIError(
                f"GLM API forbidden (status {response.status_code}).",
                status_code=response.status_code,
            )
        if response.status_code == 429:
            raise RateLimitError(
                f"GLM rate limit exceeded (status {response.status_code})."
            )
        if not response.is_success:
            raise APIError(
                f"GLM API error: {response.text}",
                status_code=response.status_code,
            )

        try:
            data = response.json()
        except json.JSONDecodeError as e:
            raise LLMError(f"GLM response was not valid JSON: {e}") from e
        choices = data.get("choices", [])
        if not choices:
            raise APIError(f"GLM returned no choices: {data}")

        # First choice's first message content
        message = choices[0].get("message", {})
        content = message.get("content", "")
        return content

    async def embed(self, text: str) -> list[float]:
        """Generate a text embedding via GLM embedding API.

        Note: GLM embedding endpoint is separate from chat completion.
        This uses the GLM embedding API.

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
            "model": "embedding-2",
            "input": text,
        }

        try:
            response = await client.post("/embeddings", json=payload)
        except httpx.TimeoutException as e:
            raise LLMError(f"GLM embedding request timed out after {self._timeout}s") from e
        except httpx.HTTPError as e:
            raise LLMError(f"GLM embedding HTTP error: {e}") from e

        if response.status_code == 401 or response.status_code == 403:
            raise AuthenticationError(
                f"GLM embedding auth failed (status {response.status_code})."
            )
        if response.status_code == 429:
            raise RateLimitError(
                f"GLM embedding rate limit exceeded (status {response.status_code})."
            )
        if not response.is_success:
            raise APIError(
                f"GLM embedding API error: {response.text}",
                status_code=response.status_code,
            )

        try:
            data = response.json()
        except json.JSONDecodeError as e:
            raise LLMError(f"GLM embedding response was not valid JSON: {e}") from e
        embeddings = data.get("data", [])
        if not embeddings:
            raise APIError(f"GLM returned no embeddings: {data}")

        return embeddings[0].get("embedding", [])


# ─────────────────────────────────────────────────────────────────────────────
# Module-level client factory (exposed for test injection via monkeypatch)
# ─────────────────────────────────────────────────────────────────────────────


def _build_client(api_key: str, timeout: float = 30.0) -> httpx.AsyncClient:
    """Build the shared httpx AsyncClient for GLM API calls.

    Extracted as a module-level function so fault-injection tests can
    replace it via ``monkeypatch.setattr(glm, \"_build_client\", ...)``.

    Args:
        api_key: GLM API key for Bearer auth.
        timeout: Request timeout in seconds.

    Returns:
        Configured ``httpx.AsyncClient`` instance.
    """
    return httpx.AsyncClient(
        base_url=GLMProvider.DEFAULT_BASE_URL,
        timeout=httpx.Timeout(timeout),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Module-level factory
# ─────────────────────────────────────────────────────────────────────────────


async def get_glm_provider() -> GLMProvider:
    """Factory function that reads config and returns a GLMProvider instance.

    Returns:
        Configured GLMProvider.
    """
    # Import here to avoid circular imports
    from src.utils.config import get_config

    config = get_config()
    glm_cfg = config.glm

    if glm_cfg is None:
        # No explicit config — rely on env vars
        return GLMProvider()

    return GLMProvider(
        api_key=glm_cfg.api_key or None,
        model=glm_cfg.model or GLMProvider.DEFAULT_MODEL,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Top-level intent analysis entry point (used by fault-tolerance tests)
# ─────────────────────────────────────────────────────────────────────────────


async def analyze_intent(
    text: str,
    *,
    provider: GLMProvider | None = None,
) -> IntentData:
    """Parse a user message into structured IntentData via GLM.

    This is the high-level entry point used by the WeChat adapter and other
    consumers. It wraps the full pipeline:
        GLMProvider.complete() → parse JSON → IntentData

    Fault-tolerance behaviour (per Sprint 2 acceptance criteria):
        All failures (transport timeout, HTTP 5xx, 401/403, rate-limit, …
        invalid JSON) are caught, logged with a ``[glm/failure/<scenario>]``
        marker, and return ``IntentData(action=IntentAction.UNKNOWN)`` as a
        degraded-but-safe result. No exception propagates to callers.

    Args:
        text: The raw user message to analyse.
        provider: Optional GLMProvider instance. If not provided, a new one
            is created using the configured API key. Accepting a provider
            enables dependency injection for unit testing.

    Returns:
        IntentData — validated structured intent, or ``IntentData(action=UNKNOWN)``
        on any failure.
    """
    # Import here to avoid circular import at module load time
    from src.domain.intent import IntentAction, IntentData
    from src.llm.intent_parser import IntentParser, IntentParsingError

    logger2 = logging.getLogger("src.llm.glm")

    try:
        if provider is None:
            provider = GLMProvider()
        parser = IntentParser(provider=provider)
        return await parser.parse(text)
    except IntentParsingError as exc:
        # IntentParser carries a specific failure marker from the underlying LLM error
        marker = getattr(exc, "failure_marker", None) or "unknown"
        logger2.exception(f"[glm/failure/{marker}] Intent parsing failed")
        return IntentData(action=IntentAction.UNKNOWN, confidence=0.0, raw_text=text)
    except AuthenticationError:
        logger2.exception("[glm/failure/http_401] API key invalid")
        return IntentData(action=IntentAction.UNKNOWN, confidence=0.0, raw_text=text)
    except RateLimitError:
        logger2.exception("[glm/failure/http_429] Rate limit exceeded")
        return IntentData(action=IntentAction.UNKNOWN, confidence=0.0, raw_text=text)
    except APIError as exc:
        if exc.status_code == 500:
            logger2.exception("[glm/failure/http_500] GLM server error")
        elif exc.status_code in (502, 503):
            logger2.exception(f"[glm/failure/http_{exc.status_code}] Gateway error")
        else:
            logger2.exception(f"[glm/failure/http_{exc.status_code}] API error")
        return IntentData(action=IntentAction.UNKNOWN, confidence=0.0, raw_text=text)
    except LLMError:
        # Covers network/timeout errors raised as LLMError subclasses
        logger2.exception("[glm/failure/llm_error] LLM error")
        return IntentData(action=IntentAction.UNKNOWN, confidence=0.0, raw_text=text)
    except Exception:
        # Defensive: any unexpected error must not propagate
        logger2.exception("[glm/failure/unknown] Unexpected error in analyze_intent")
        return IntentData(action=IntentAction.UNKNOWN, confidence=0.0, raw_text=text)
