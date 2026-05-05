"""Smoke tests for the headless pygame renderer (Phase 9)."""

from __future__ import annotations

import pytest


def test_pygame_renderer_smoke() -> None:
    """End-to-end: import, init, draw a frame, close — all in headless mode."""
    pytest.importorskip("pygame")

    from src.envs import DummyOvercookedEnv
    from src.envs.render_pygame import PygameRenderer

    env = DummyOvercookedEnv()
    obs = env.reset(seed=0)

    renderer = PygameRenderer(width=5, height=5, headless=True)
    try:
        renderer.draw(env, obs, last_reward=0.0)
        # Step once and re-draw to exercise the held-item / pot updates.
        step = env.step({"agent_0": 5, "agent_1": 0})
        renderer.draw(env, step.obs, last_reward=sum(step.rewards.values()))
    finally:
        renderer.close()


def test_pygame_renderer_poll_events_headless() -> None:
    """`poll_events` must return a structured dict even with no display."""
    pytest.importorskip("pygame")

    from src.envs.render_pygame import PygameRenderer

    renderer = PygameRenderer(width=5, height=5, headless=True)
    try:
        events = renderer.poll_events()
        assert "quit" in events and isinstance(events["quit"], bool)
        assert "pressed" in events and isinstance(events["pressed"], set)
        assert "just_pressed" in events and isinstance(events["just_pressed"], set)
    finally:
        renderer.close()


def test_extract_render_info_uses_env_attributes() -> None:
    """The introspection path must read `_positions` / `_held` from the dummy env."""
    pytest.importorskip("pygame")

    from src.envs import DummyOvercookedEnv
    from src.envs.render_pygame import _extract_render_info

    env = DummyOvercookedEnv()
    obs = env.reset(seed=0)
    info = _extract_render_info(env, obs)
    assert "agent_0" in info.positions
    assert "agent_1" in info.positions
    # 5x5 dummy grid.
    assert info.grid_width == 5 and info.grid_height == 5
    # No pot onions yet at reset.
    assert info.pots and info.pots[0][2] == 0
