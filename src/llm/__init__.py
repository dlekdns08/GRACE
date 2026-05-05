"""Public API for the LLM layer.

The rollout/training code should only need to import from this package
root; concrete modules are an implementation detail.
"""

from .async_client import AsyncLLMClient
from .cache import CachedLLMClient
from .client import LLMClient, LLMRequest, LLMResponse, LMStudioClient
from .mock import MockLLMClient
from .parsers import parse_subgoal, parse_subgoal_with_validation
from .prompts import (
    PROMPT_VERSION,
    SUBGOAL_ENUM,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_V1,
    SYSTEM_PROMPT_V2,
    build_request,
    build_user_prompt,
    get_system_prompt,
)

__all__ = [
    "PROMPT_VERSION",
    "SUBGOAL_ENUM",
    "SYSTEM_PROMPT",
    "SYSTEM_PROMPT_V1",
    "SYSTEM_PROMPT_V2",
    "AsyncLLMClient",
    "CachedLLMClient",
    "LLMClient",
    "LLMRequest",
    "LLMResponse",
    "LMStudioClient",
    "MockLLMClient",
    "build_request",
    "build_user_prompt",
    "get_system_prompt",
    "parse_subgoal",
    "parse_subgoal_with_validation",
]
