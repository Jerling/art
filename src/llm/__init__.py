"""LLM providers and intent parsing.

ADR-001: LLM layer is model-agnostic via the LLMProvider protocol.
Default provider: MiniMax (MiniMax-M2.7 / MiniMax-Text-01).
"""
from src.llm.intent_parser import (
    IntentParsingError,
    IntentParser,
    get_intent_parser,
)
from src.llm.minimax import (
    APIError,
    AuthenticationError,
    LLMError,
    LLMProvider,
    MiniMaxProvider,
    RateLimitError,
    analyze_intent,
    get_minimax_provider,
)

__all__ = [
    # Protocol
    "LLMProvider",
    # Errors
    "LLMError",
    "AuthenticationError",
    "RateLimitError",
    "APIError",
    # MiniMax
    "MiniMaxProvider",
    "get_minimax_provider",
    "analyze_intent",
    # Intent Parser
    "IntentParser",
    "IntentParsingError",
    "get_intent_parser",
]
