"""Shared LLM error classes and base protocol.

ADR-001: LLM layer is model-agnostic via the LLMProvider protocol.
All provider implementations (GLM, MiniMax, etc.) use these shared errors.
"""
from __future__ import annotations

from abc import abstractmethod
from typing import Protocol


class LLMProvider(Protocol):
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
