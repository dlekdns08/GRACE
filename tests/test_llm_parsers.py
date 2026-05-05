"""Unit tests for `src/llm/parsers.py`.

Covers happy path, markdown-fenced output, malformed strings, and wrong
value types. The parser must never raise; it returns `None` instead.
"""

from __future__ import annotations

from src.llm.parsers import parse_subgoal


def test_parse_valid_subgoal() -> None:
    response = '{"agent_a": "go_to_pot", "agent_b": "fetch_dish"}'
    assert parse_subgoal(response) == {
        "agent_a": "go_to_pot",
        "agent_b": "fetch_dish",
    }


def test_parse_with_markdown_fence() -> None:
    response = '```json\n{"agent_a": "go_to_pot", "agent_b": "fetch_dish"}\n```'
    assert parse_subgoal(response) == {
        "agent_a": "go_to_pot",
        "agent_b": "fetch_dish",
    }


def test_parse_with_plain_markdown_fence() -> None:
    response = '```\n{"agent_a": "idle"}\n```'
    assert parse_subgoal(response) == {"agent_a": "idle"}


def test_parse_malformed_returns_none() -> None:
    assert parse_subgoal("uhh I think...") is None
    assert parse_subgoal("{not valid json") is None
    assert parse_subgoal("") is None
    assert parse_subgoal("   ") is None


def test_parse_wrong_types_returns_none() -> None:
    # Integer value
    assert parse_subgoal('{"agent_a": 1}') is None
    # List value
    assert parse_subgoal('{"agent_a": ["go_to_pot"]}') is None
    # Top-level list (not a dict)
    assert parse_subgoal('["go_to_pot", "fetch_dish"]') is None
    # Top-level scalar
    assert parse_subgoal('"go_to_pot"') is None
    # Nested dict value
    assert parse_subgoal('{"agent_a": {"do": "go_to_pot"}}') is None
