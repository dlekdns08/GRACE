"""Unit tests for ``state_to_text``."""

from __future__ import annotations

from src.envs.state_text import (
    GenericPlayer,
    GenericPot,
    GenericState,
    state_to_text,
)


def _make_state(
    *,
    pot_onions: int = 2,
    cooking: int = 0,
    ready: bool = False,
    players: list[GenericPlayer] | None = None,
) -> GenericState:
    if players is None:
        players = [
            GenericPlayer(name="agent_0", position=(0, 0), held_item=None),
            GenericPlayer(name="agent_1", position=(4, 4), held_item="onion"),
        ]
    return GenericState(
        timestep=12,
        max_steps=400,
        score=3,
        soups_served=1,
        players=players,
        pots=[
            GenericPot(
                onion_count=pot_onions,
                cooking_time_left=cooking,
                is_ready=ready,
            )
        ],
    )


def test_deterministic() -> None:
    state = _make_state()
    assert state_to_text(state) == state_to_text(state)


def test_distinguishes_pot_states() -> None:
    s1 = _make_state(pot_onions=2, cooking=0, ready=False)
    s2 = _make_state(pot_onions=3, cooking=5, ready=False)
    assert state_to_text(s1) != state_to_text(s2)


def test_holds_token_budget() -> None:
    state = _make_state()
    text = state_to_text(state)
    assert len(text) < 600, f"text too long ({len(text)} chars):\n{text}"


def test_sorts_agents_consistently() -> None:
    a = GenericPlayer(name="agent_0", position=(0, 0), held_item=None)
    b = GenericPlayer(name="agent_1", position=(4, 4), held_item="onion")
    s_forward = _make_state(players=[a, b])
    s_reverse = _make_state(players=[b, a])
    assert state_to_text(s_forward) == state_to_text(s_reverse)


def test_pot_states_render_expected_phrases() -> None:
    """Sanity check the four pot rendering branches are reachable."""
    empty = _make_state(pot_onions=0)
    cooking = _make_state(pot_onions=3, cooking=4, ready=False)
    ready = _make_state(pot_onions=3, cooking=0, ready=True)

    assert "empty" in state_to_text(empty)
    assert "cooking, 4s remaining" in state_to_text(cooking)
    assert "ready to serve" in state_to_text(ready)
    assert "2/3 onions, not started" in state_to_text(_make_state(pot_onions=2))
