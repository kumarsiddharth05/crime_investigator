"""LLM subsystem package initialization."""

from src.llm.client import (
    DEFAULT_TEMPERATURE,
    DEFAULT_TIMEOUT_SECONDS,
    LLMAuthenticationError,
    LLMClient,
    LLMClientError,
    LLMConfigurationError,
    LLMConfig,
    LLMRateLimitError,
    LLMResponse,
    LLMTransportError,
    validate_response_shape,
)
from src.llm.prompt_builder import (
    PERMITTED_TIER_B_TYPES,
    PromptBundle,
    build_prompt,
    sanitize_case_context,
)

__all__ = [
    "DEFAULT_TEMPERATURE",
    "DEFAULT_TIMEOUT_SECONDS",
    "LLMAuthenticationError",
    "LLMClient",
    "LLMClientError",
    "LLMConfigurationError",
    "LLMConfig",
    "LLMRateLimitError",
    "LLMResponse",
    "LLMTransportError",
    "PERMITTED_TIER_B_TYPES",
    "PromptBundle",
    "build_prompt",
    "sanitize_case_context",
    "validate_response_shape",
]
