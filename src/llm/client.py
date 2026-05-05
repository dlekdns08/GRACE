"""Core LLM client abstractions and the LM Studio implementation.

This module defines the protocol that every LLM backend must satisfy
(`LLMClient`) along with the request/response dataclasses that carry the
inputs and outputs around. Concrete implementations live next to this file
(`mock.py`, `cache.py`, `async_client.py`).

No I/O happens at import time; constructing `LMStudioClient` only stores
configuration. The actual HTTP call happens inside `call`.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from openai import OpenAI


@dataclass(slots=True)
class LLMRequest:
    """A request to an LLM backend.

    `metadata` is intended for logging only (episode id, step, etc.) and is
    *not* included in cache keys or sent to the model.
    """

    prompt: str
    system: str | None = None
    temperature: float = 0.0
    max_tokens: int = 512
    seed: int | None = None
    metadata: dict | None = field(default_factory=dict)


@dataclass(slots=True)
class LLMResponse:
    """The response returned by an LLM backend."""

    text: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    cached: bool
    request_id: str


@runtime_checkable
class LLMClient(Protocol):
    """Duck-typed protocol every LLM backend must satisfy.

    Implementations are injected into the rollout loop, so anything that
    quacks like this protocol (mock, cache wrapper, real client) is fine.
    """

    def call(self, req: LLMRequest) -> LLMResponse: ...

    async def call_async(self, req: LLMRequest) -> LLMResponse: ...


class LMStudioClient:
    """Client for LM Studio (or any OpenAI-compatible server).

    The actual network connection is created lazily by the OpenAI SDK when
    `call` first runs, so importing this module is side-effect free.
    """

    def __init__(self, base_url: str, model: str, timeout: float = 30.0) -> None:
        self.client = OpenAI(base_url=base_url, api_key="local", timeout=timeout)
        self.model = model
        self.timeout = timeout

    def call(self, req: LLMRequest) -> LLMResponse:
        start = time.perf_counter()
        messages: list[dict] = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.append({"role": "user", "content": req.prompt})

        resp = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=req.temperature,
            max_tokens=req.max_tokens,
            seed=req.seed,
        )
        latency_ms = (time.perf_counter() - start) * 1000.0

        text = resp.choices[0].message.content or ""
        usage = resp.usage
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

        return LLMResponse(
            text=text,
            latency_ms=latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached=False,
            request_id=resp.id,
        )

    async def call_async(self, req: LLMRequest) -> LLMResponse:
        # Simple bridge: run the sync call on a worker thread so the event
        # loop is not blocked. Heavier async wrappers live in async_client.py.
        return await asyncio.to_thread(self.call, req)
