"""Unit tests for `src/llm/cache.py`.

Uses `MockLLMClient` so no LLM is contacted. Verifies the basic cache
contract: hits skip the inner client, version bumps invalidate, and
`stats()` reports correct counts.
"""

from __future__ import annotations

from src.llm.cache import CachedLLMClient
from src.llm.client import LLMRequest
from src.llm.mock import MockLLMClient


def _make_request(prompt: str = "hello") -> LLMRequest:
    return LLMRequest(prompt=prompt, system="sys", temperature=0.0, seed=0)


def test_first_call_misses_second_call_hits() -> None:
    inner = MockLLMClient(["resp-1", "resp-2"])
    cache = CachedLLMClient(inner, prompt_version="v1")

    req = _make_request()
    first = cache.call(req)
    second = cache.call(req)

    assert first.cached is False
    assert second.cached is True
    # The second response must reuse the stored text, not advance the mock.
    assert second.text == first.text == "resp-1"
    # The mock was only called once.
    assert inner.call_count == 1
    # Cached responses report the sentinel latency.
    assert second.latency_ms == 0.1


def test_different_prompt_version_invalidates_cache() -> None:
    inner = MockLLMClient(["resp-a", "resp-b"])

    cache_v1 = CachedLLMClient(inner, prompt_version="v1")
    cache_v2 = CachedLLMClient(inner, prompt_version="v2")

    req = _make_request()
    r1 = cache_v1.call(req)
    r2 = cache_v2.call(req)

    # Both are cache misses against their respective versions and both
    # advanced the inner mock.
    assert r1.cached is False
    assert r2.cached is False
    assert r1.text == "resp-a"
    assert r2.text == "resp-b"
    assert inner.call_count == 2


def test_stats_reports_correct_counts() -> None:
    inner = MockLLMClient(["resp-1"])
    cache = CachedLLMClient(inner, prompt_version="v1")

    req_a = _make_request("prompt-a")
    req_b = _make_request("prompt-b")

    # 2 misses (different prompts), then 2 hits, then 1 more miss.
    cache.call(req_a)
    cache.call(req_b)
    cache.call(req_a)
    cache.call(req_b)
    cache.call(_make_request("prompt-c"))

    stats = cache.stats()
    assert stats == {"hits": 2, "misses": 3, "size": 3}
