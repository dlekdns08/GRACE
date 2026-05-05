"""Smoke tests for the in-memory DummyOvercookedEnv."""

from __future__ import annotations

import numpy as np

from src.envs import DummyOvercookedEnv, EnvObservation


def test_dummy_env_resets() -> None:
    env = DummyOvercookedEnv()
    obs = env.reset(seed=0)
    assert isinstance(obs, EnvObservation)
    assert set(obs.raw.keys()) == set(env.agent_ids)
    for vec in obs.raw.values():
        assert isinstance(vec, np.ndarray)
        assert vec.shape == (env.obs_dim,)
    assert isinstance(obs.text, str) and len(obs.text) > 0


def test_dummy_env_runs_50_steps_random() -> None:
    env = DummyOvercookedEnv()
    env.reset(seed=42)
    rng = np.random.default_rng(42)

    terminated = False
    truncated = False
    for _ in range(50):
        actions = {aid: int(rng.integers(0, env.action_space_size)) for aid in env.agent_ids}
        step = env.step(actions)
        terminated = step.terminated
        truncated = step.truncated
        if terminated or truncated:
            break

    assert terminated or truncated, "episode neither terminated nor truncated within 50 steps"


def test_dummy_env_obs_shape() -> None:
    env = DummyOvercookedEnv()
    obs = env.reset(seed=1)
    assert env.obs_dim == 8
    for aid in env.agent_ids:
        assert obs.raw[aid].shape == (8,)
        assert obs.raw[aid].dtype == np.float32


def test_dummy_env_action_space() -> None:
    env = DummyOvercookedEnv()
    assert env.action_space_size == 6
    # All legal action indices are accepted.
    env.reset(seed=2)
    for action in range(env.action_space_size):
        env.reset(seed=2)
        env.step({aid: action for aid in env.agent_ids})


def test_dummy_env_truncates_without_progress() -> None:
    env = DummyOvercookedEnv()
    env.reset(seed=3)
    last = None
    for _ in range(50):
        last = env.step({aid: 0 for aid in env.agent_ids})  # all noop
        if last.terminated or last.truncated:
            break
    assert last is not None
    assert last.truncated and not last.terminated
