"""Unit tests for :mod:`src.llm.latency`.

The latency helpers are the smoke-check that DESIGN section 4.4 calls
for: "verify async LLM doesn't block the RL loop". We hit them with a
tiny :class:`MockLLMClient` so the tests stay fast.
"""

from __future__ import annotations

import math

from src.llm.async_client import AsyncLLMClient
from src.llm.client import LLMRequest, LLMResponse
from src.llm.latency import (
    LatencyStats,
    measure_async_overlap,
    measure_sync,
    summarize,
)
from src.llm.mock import MockLLMClient


def _fake_response(latency_ms: float, *, cached: bool = False) -> LLMResponse:
    return LLMResponse(
        text="dummy",
        latency_ms=latency_ms,
        prompt_tokens=10,
        completion_tokens=5,
        cached=cached,
        request_id="t",
    )


def _make_request(prompt: str = "hi") -> LLMRequest:
    return LLMRequest(prompt=prompt, system="sys", temperature=0.0, seed=0)


def test_summarize_basic() -> None:
    records = [
        _fake_response(10.0),
        _fake_response(20.0),
        _fake_response(30.0, cached=True),
        _fake_response(40.0),
        _fake_response(50.0),
    ]
    stats = summarize(records)

    assert isinstance(stats, LatencyStats)
    assert stats.n == 5
    assert math.isclose(stats.mean_ms, 30.0)
    assert math.isclose(stats.p50_ms, 30.0)
    assert math.isclose(stats.max_ms, 50.0)
    assert stats.p95_ms >= stats.p50_ms
    assert stats.p99_ms >= stats.p95_ms
    assert math.isclose(stats.cached_frac, 1 / 5)
    # 10 prompt + 5 completion tokens per request = 50 prompt + 25 completion total
    # over 150ms = 0.15s -> ~333 prompt tok/s and ~167 completion tok/s.
    assert stats.tokens_per_sec_in > 0.0
    assert stats.tokens_per_sec_out > 0.0
    assert math.isfinite(stats.tokens_per_sec_in)
    assert math.isfinite(stats.tokens_per_sec_out)


def test_summarize_empty() -> None:
    stats = summarize([])
    assert stats.n == 0
    for field_name in (
        "mean_ms",
        "p50_ms",
        "p95_ms",
        "p99_ms",
        "max_ms",
        "cached_frac",
        "tokens_per_sec_in",
        "tokens_per_sec_out",
    ):
        assert getattr(stats, field_name) == 0.0


def test_summarize_single_record() -> None:
    stats = summarize([_fake_response(42.0)])
    assert stats.n == 1
    assert math.isclose(stats.mean_ms, 42.0)
    assert math.isclose(stats.p50_ms, 42.0)
    assert math.isclose(stats.p99_ms, 42.0)
    assert math.isclose(stats.max_ms, 42.0)


def test_measure_sync_with_mock() -> None:
    inner = MockLLMClient(['{"agent_0": "go_to_onion", "agent_1": "go_to_onion"}'])
    requests = [_make_request(f"req-{i}") for i in range(10)]

    stats = measure_sync(inner, requests)

    assert isinstance(stats, LatencyStats)
    assert stats.n == 10
    assert stats.cached_frac == 0.0  # MockLLMClient never marks cached
    # Mock returns latency_ms=0.0 so the percentiles are all zero -- but they
    # must still be finite and non-negative.
    for field_name in ("mean_ms", "p50_ms", "p95_ms", "p99_ms", "max_ms"):
        value = getattr(stats, field_name)
        assert math.isfinite(value) and value >= 0.0


def test_measure_async_overlap_runs() -> None:
    inner = MockLLMClient(['{"agent_0": "idle", "agent_1": "idle"}'])
    async_client = AsyncLLMClient(inner, max_workers=2)
    try:
        requests = [_make_request(f"req-{i}") for i in range(5)]
        result = measure_async_overlap(
            async_client, requests, work_per_step_ms=5.0
        )
    finally:
        async_client.shutdown(wait=True)

    expected_keys = {
        "wall_time_ms",
        "foreground_blocked_ms",
        "lost_overlap_frac",
        "n_requests",
    }
    assert set(result.keys()) == expected_keys

    for key, value in result.items():
        assert math.isfinite(value), f"{key} not finite: {value!r}"
        assert value >= 0.0, f"{key} negative: {value!r}"

    assert result["n_requests"] == 5.0
    # lost_overlap_frac must remain in [0, 1] by construction.
    assert 0.0 <= result["lost_overlap_frac"] <= 1.0


def test_measure_async_overlap_zero_work_still_returns_finite() -> None:
    """work_per_step_ms=0 means we never sleep; result must still be finite."""
    inner = MockLLMClient(['{"agent_0": "idle", "agent_1": "idle"}'])
    async_client = AsyncLLMClient(inner, max_workers=1)
    try:
        requests = [_make_request("only")]
        result = measure_async_overlap(
            async_client, requests, work_per_step_ms=0.0
        )
    finally:
        async_client.shutdown(wait=True)

    assert result["n_requests"] == 1.0
    assert math.isfinite(result["wall_time_ms"])
    assert math.isfinite(result["foreground_blocked_ms"])
    assert 0.0 <= result["lost_overlap_frac"] <= 1.0
