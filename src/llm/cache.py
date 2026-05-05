"""Prompt-hash cache wrapper around any `LLMClient`.

Identical (system, prompt, temperature, seed) inputs return the same
response without re-calling the inner client. The cache key includes
`prompt_version`, so bumping the version automatically invalidates the
whole cache rather than serving stale answers from a different prompt.
"""

from __future__ import annotations

import asyncio
import hashlib
from dataclasses import replace

from .client import LLMClient, LLMRequest, LLMResponse


class CachedLLMClient:
    """Wraps an inner LLM client with a sha256-keyed dict cache.

    Cache hits return a *copy* of the stored response with `cached=True`
    and `latency_ms=0.1`, leaving the original entry untouched so repeat
    hits stay consistent.
    """

    def __init__(self, inner: LLMClient, prompt_version: str) -> None:
        self.inner = inner
        self.prompt_version = prompt_version
        self.cache: dict[str, LLMResponse] = {}
        self.hits: int = 0
        self.misses: int = 0

    def _key(self, req: LLMRequest) -> str:
        material = (
            f"{self.prompt_version}|{req.system}|{req.prompt}"
            f"|{req.temperature}|{req.seed}"
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def call(self, req: LLMRequest) -> LLMResponse:
        key = self._key(req)
        cached = self.cache.get(key)
        if cached is not None:
            self.hits += 1
            return replace(cached, cached=True, latency_ms=0.1)

        self.misses += 1
        resp = self.inner.call(req)
        self.cache[key] = resp
        return resp

    async def call_async(self, req: LLMRequest) -> LLMResponse:
        key = self._key(req)
        cached = self.cache.get(key)
        if cached is not None:
            self.hits += 1
            return replace(cached, cached=True, latency_ms=0.1)

        self.misses += 1
        # Prefer the inner client's native async path when present;
        # otherwise bridge through a worker thread.
        inner_async = getattr(self.inner, "call_async", None)
        if inner_async is not None:
            resp = await inner_async(req)
        else:
            resp = await asyncio.to_thread(self.inner.call, req)
        self.cache[key] = resp
        return resp

    def stats(self) -> dict[str, int]:
        return {"hits": self.hits, "misses": self.misses, "size": len(self.cache)}
