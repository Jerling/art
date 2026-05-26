"""LLM providers and intent parsing.

ADR-001: LLM layer is model-agnostic via the LLMProvider protocol.
Default provider: GLM (glm-4.6-flash).
"""
from src.llm.base import (
    APIError,
    AuthenticationError,
    LLMError,
    LLMProvider,
    RateLimitError,
)
from src.llm.glm import (
    GLMProvider,
    get_glm_provider,
)
from src.llm.glm import (
    analyze_intent as glm_analyze_intent,
)
from src.llm.intent_parser import (
    IntentParser,
    IntentParsingError,
    get_intent_parser,
)
from src.llm.minimax import (
    MiniMaxProvider,
    get_minimax_provider,
)
from src.llm.minimax import (
    analyze_intent as minimax_analyze_intent,
)

__all__ = [
    # Protocol
    "LLMProvider",
    # Errors
    "LLMError",
    "AuthenticationError",
    "RateLimitError",
    "APIError",
    # GLM
    "GLMProvider",
    "get_glm_provider",
    "glm_analyze_intent",
    # MiniMax
    "MiniMaxProvider",
    "get_minimax_provider",
    "minimax_analyze_intent",
    # Intent Parser
    "IntentParser",
    "IntentParsingError",
    "get_intent_parser",
]
