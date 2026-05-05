"""Tests for subgoal validation against the closed enum.

These exercise both the new strict parser
(:func:`src.llm.parsers.parse_subgoal_with_validation`) and the
rollout-side fallback (:func:`src.training.rollout._validate_subgoal_dict`)
that drops invalid values rather than aborting the rollout.
"""

from __future__ import annotations

from src.llm.parsers import parse_subgoal_with_validation
from src.llm.prompts import SUBGOAL_ENUM
from src.training.rollout import _validate_subgoal_dict


_AGENTS: list[str] = ["agent_0", "agent_1"]


def test_invalid_subgoal_replaced_with_none() -> None:
    """Both agents emit unknown values: validator returns ``None``."""
    parsed = {"agent_0": "fly_away", "agent_1": "teleport"}
    cleaned, n_invalid = _validate_subgoal_dict(parsed, _AGENTS)
    assert cleaned is None
    assert n_invalid == 2


def test_partial_validity() -> None:
    """One agent valid, one invalid → invalid agent dropped."""
    parsed = {"agent_0": "go_to_onion", "agent_1": "fly_away"}
    cleaned, n_invalid = _validate_subgoal_dict(parsed, _AGENTS)
    assert cleaned == {"agent_0": "go_to_onion"}
    assert n_invalid == 1


def test_all_invalid_returns_empty_dict() -> None:
    """All invalid → ``None`` (so the rollout uses the previous subgoal)."""
    parsed = {"agent_0": "??", "agent_1": "###"}
    cleaned, n_invalid = _validate_subgoal_dict(parsed, _AGENTS)
    assert cleaned is None
    assert n_invalid == 2


def test_validate_none_input() -> None:
    """``None`` parser output passes through cleanly."""
    cleaned, n_invalid = _validate_subgoal_dict(None, _AGENTS)
    assert cleaned is None
    assert n_invalid == 0


def test_strict_parser_accepts_valid_response() -> None:
    """Strict parser returns a dict for an in-enum response."""
    text = '{"agent_0": "go_to_onion", "agent_1": "pickup_dish"}'
    parsed = parse_subgoal_with_validation(text, _AGENTS)
    assert parsed == {"agent_0": "go_to_onion", "agent_1": "pickup_dish"}


def test_strict_parser_rejects_unknown_value() -> None:
    text = '{"agent_0": "go_to_onion", "agent_1": "fly_away"}'
    assert parse_subgoal_with_validation(text, _AGENTS) is None


def test_strict_parser_rejects_missing_agent() -> None:
    text = '{"agent_0": "go_to_onion"}'
    assert parse_subgoal_with_validation(text, _AGENTS) is None


def test_strict_parser_default_enum_matches_prompts() -> None:
    """Sanity: the parser's default enum is exactly :data:`SUBGOAL_ENUM`."""
    # An exotic value that is *not* in the enum should be rejected by the
    # default-enum path.
    bogus = '{"agent_0": "foo", "agent_1": "bar"}'
    assert parse_subgoal_with_validation(bogus, _AGENTS) is None
    # Whereas explicitly allowing them lets it through.
    allowed = list(SUBGOAL_ENUM) + ["foo", "bar"]
    assert parse_subgoal_with_validation(bogus, _AGENTS, valid_subgoals=allowed) == {
        "agent_0": "foo",
        "agent_1": "bar",
    }


def test_strict_parser_drops_extra_agents() -> None:
    """Extra keys in the response are silently dropped (not an error)."""
    text = '{"agent_0": "go_to_onion", "agent_1": "pickup_dish", "agent_2": "idle"}'
    out = parse_subgoal_with_validation(text, _AGENTS)
    assert out == {"agent_0": "go_to_onion", "agent_1": "pickup_dish"}
