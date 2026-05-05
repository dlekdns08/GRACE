"""A deterministic mock LLM client used by tests and CI.

Cycles through a list of preset response strings. Never makes a network
call, so it is safe to use anywhere we would otherwise need an LLM.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from .client import LLMRequest, LLMResponse


class MockLLMClient:
    """Returns preset responses in a deterministic cycle.

    Each `call` increments `self.call_count`. The `request_id` is
    `f"mock-{n}"` where `n` is the post-increment value of `call_count`,
    so the first call has id `mock-1`.
    """

    def __init__(self, responses: Sequence[str]) -> None:
        if not responses:
            raise ValueError("MockLLMClient requires at least one response")
        self.responses: list[str] = list(responses)
        self.call_count: int = 0

    def call(self, req: LLMRequest) -> LLMResponse:
        text = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        return LLMResponse(
            text=text,
            latency_ms=0.0,
            prompt_tokens=10,
            completion_tokens=5,
            cached=False,
            request_id=f"mock-{self.call_count}",
        )

    async def call_async(self, req: LLMRequest) -> LLMResponse:
        return await asyncio.to_thread(self.call, req)
