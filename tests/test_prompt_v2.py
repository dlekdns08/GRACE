"""Unit tests for prompt v2.

Confirms that:
* :data:`PROMPT_VERSION` is now ``"v2"``.
* v1 is preserved verbatim and reachable via :func:`get_system_prompt`.
* The v2 system prompt mentions every enum subgoal and the example
  section markers.
* :func:`build_request` defaults to v2 but can opt into v1.
* The :class:`CachedLLMClient` correctly invalidates between versions.
"""

from __future__ import annotations

import re

from src.llm.cache import CachedLLMClient
from src.llm.client import LLMRequest
from src.llm.mock import MockLLMClient
from src.llm.prompts import (
    PROMPT_VERSION,
    SUBGOAL_ENUM,
    SYSTEM_PROMPT,
    SYSTEM_PROMPT_V1,
    SYSTEM_PROMPT_V2,
    build_request,
    get_system_prompt,
)


def test_prompt_version_is_v2() -> None:
    assert PROMPT_VERSION == "v2"
    # v1 must still be reachable via the selector.
    assert get_system_prompt("v1") == SYSTEM_PROMPT_V1
    assert get_system_prompt("v2") == SYSTEM_PROMPT_V2
    # Default exported SYSTEM_PROMPT is v2.
    assert SYSTEM_PROMPT == SYSTEM_PROMPT_V2


def test_v2_system_prompt_mentions_enum() -> None:
    for subgoal in SUBGOAL_ENUM:
        assert subgoal in SYSTEM_PROMPT_V2, f"missing enum value {subgoal!r} in v2 prompt"


def test_v2_system_prompt_has_examples() -> None:
    # Case-insensitive match for at least three "Example" markers.
    matches = re.findall(r"example", SYSTEM_PROMPT_V2, flags=re.IGNORECASE)
    assert len(matches) >= 3, f"expected >=3 'Example' markers, found {len(matches)}"


def test_build_request_uses_v2_by_default() -> None:
    req = build_request(state_text="dummy", agent_ids=["agent_0", "agent_1"])
    assert req.system == SYSTEM_PROMPT_V2

    # Opt-in to v1 explicitly:
    req_v1 = build_request(
        state_text="dummy",
        agent_ids=["agent_0", "agent_1"],
        prompt_version="v1",
    )
    assert req_v1.system == SYSTEM_PROMPT_V1


def test_v1_v2_distinct() -> None:
    assert SYSTEM_PROMPT_V1 != SYSTEM_PROMPT_V2


def test_get_system_prompt_unknown_version_raises() -> None:
    try:
        get_system_prompt("v99")
    except ValueError as exc:
        assert "v99" in str(exc)
    else:
        raise AssertionError("expected ValueError for unknown prompt version")


def test_cache_invalidates_across_versions() -> None:
    """A request built with v1 then v2 should miss the cache twice.

    We use the same ``CachedLLMClient`` instance (one prompt_version) and
    feed it two requests whose ``system`` strings differ -- since cache
    keys include the system prompt, both calls must miss.
    """
    inner = MockLLMClient(["resp-a", "resp-b"])
    cache = CachedLLMClient(inner, prompt_version=PROMPT_VERSION)

    req_v1 = build_request(
        state_text="state-x",
        agent_ids=["agent_0", "agent_1"],
        prompt_version="v1",
    )
    req_v2 = build_request(
        state_text="state-x",
        agent_ids=["agent_0", "agent_1"],
        prompt_version="v2",
    )
    assert req_v1.system != req_v2.system

    r1 = cache.call(req_v1)
    r2 = cache.call(req_v2)

    assert r1.cached is False
    assert r2.cached is False
    assert r1.text == "resp-a"
    assert r2.text == "resp-b"
    assert inner.call_count == 2
    assert cache.stats() == {"hits": 0, "misses": 2, "size": 2}


def test_cache_invalidates_across_cache_versions() -> None:
    """Bumping the wrapper's ``prompt_version`` also invalidates."""
    inner = MockLLMClient(["resp-a", "resp-b"])

    req = LLMRequest(prompt="hello", system="sys", temperature=0.0, seed=0)

    cache_v1 = CachedLLMClient(inner, prompt_version="v1")
    cache_v2 = CachedLLMClient(inner, prompt_version="v2")

    r1 = cache_v1.call(req)
    r2 = cache_v2.call(req)

    assert r1.cached is False
    assert r2.cached is False
    assert r1.text == "resp-a"
    assert r2.text == "resp-b"
    assert inner.call_count == 2
