"""Unit tests for `src/llm/mock.py`.

The mock client is the foundation of every other LLM-related test, so
its cycling and counting behavior must be ironclad.
"""

from __future__ import annotations

import asyncio

import pytest

from src.llm.client import LLMRequest
from src.llm.mock import MockLLMClient


def _req() -> LLMRequest:
    return LLMRequest(prompt="anything")


def test_call_count_increments() -> None:
    client = MockLLMClient(["a"])
    assert client.call_count == 0
    client.call(_req())
    assert client.call_count == 1
    client.call(_req())
    assert client.call_count == 2


def test_responses_cycle_in_order() -> None:
    client = MockLLMClient(["a", "b", "c"])
    texts = [client.call(_req()).text for _ in range(7)]
    assert texts == ["a", "b", "c", "a", "b", "c", "a"]


def test_request_id_uses_call_count() -> None:
    client = MockLLMClient(["a", "b"])
    r1 = client.call(_req())
    r2 = client.call(_req())
    assert r1.request_id == "mock-1"
    assert r2.request_id == "mock-2"


def test_response_token_fields_are_constants() -> None:
    client = MockLLMClient(["a"])
    resp = client.call(_req())
    assert resp.prompt_tokens == 10
    assert resp.completion_tokens == 5
    assert resp.cached is False
    assert resp.latency_ms == 0.0


def test_call_async_matches_sync_behavior() -> None:
    client = MockLLMClient(["a", "b"])

    async def _go() -> list[str]:
        r1 = await client.call_async(_req())
        r2 = await client.call_async(_req())
        return [r1.text, r2.text]

    assert asyncio.run(_go()) == ["a", "b"]
    assert client.call_count == 2


def test_empty_responses_raises() -> None:
    with pytest.raises(ValueError):
        MockLLMClient([])
