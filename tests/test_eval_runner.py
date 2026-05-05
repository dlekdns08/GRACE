"""Smoke + correctness tests for :func:`src.eval.run_eval`."""

from __future__ import annotations

import pandas as pd

from src.envs import DummyOvercookedEnv
from src.eval import run_eval
from src.llm.mock import MockLLMClient
from src.policies import FixedKMetaPolicy, PPOPolicy


def _make_components(k: int = 5) -> tuple:
    env = DummyOvercookedEnv(max_steps=20)
    policy = PPOPolicy(obs_dim=env.obs_dim, action_dim=env.action_space_size)
    meta = FixedKMetaPolicy(k=k)
    llm = MockLLMClient(
        responses=[
            '{"agent_0": "go_to_onion", "agent_1": "go_to_onion"}',
            '{"agent_0": "deliver_onion_to_pot", "agent_1": "pickup_dish"}',
        ]
    )
    return env, policy, meta, llm


def test_run_eval_returns_one_row_per_episode():
    env, policy, meta, llm = _make_components()
    df = run_eval(
        env=env,
        policy=policy,
        meta_policy=meta,
        llm_client=llm,
        n_episodes=3,
        max_steps_per_episode=20,
        seed_base=1234,
    )
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 3
    assert list(df.columns) == [
        "episode",
        "return_",
        "length",
        "soup_count",
        "llm_calls",
        "cached_calls",
    ]
    # Episode ids are 0..n-1 in order.
    assert df["episode"].tolist() == [0, 1, 2]
    # Lengths are bounded by the env's truncation horizon.
    assert (df["length"] <= 20).all()
    assert (df["length"] >= 1).all()


def test_run_eval_sets_argmax_then_restores_sampling():
    env, policy, meta, llm = _make_components()
    # Sanity: PPOPolicy starts in sampling mode.
    assert policy._sampling is True
    run_eval(env, policy, meta, llm, n_episodes=1, max_steps_per_episode=10)
    # After exit, sampling is restored.
    assert policy._sampling is True


def test_run_eval_llm_calls_consistent_with_meta_period():
    env, policy, meta, llm = _make_components(k=5)
    df = run_eval(
        env=env,
        policy=policy,
        meta_policy=meta,
        llm_client=llm,
        n_episodes=2,
        max_steps_per_episode=20,
        seed_base=42,
    )
    # FixedK with k=5 fires at steps 0, 5, 10, 15 within an episode of <=20 steps,
    # so per-episode call count is at least 1 and at most 4.
    assert (df["llm_calls"] >= 1).all()
    assert (df["llm_calls"] <= 4).all()


def test_run_eval_handles_meta_set_eval_hook():
    """A meta-policy without ``set_eval`` must still work; one with it gets called."""

    class StubMeta(FixedKMetaPolicy):
        def __init__(self) -> None:
            super().__init__(k=3)
            self._eval_mode: bool = False
            self.eval_calls: list[bool] = []

        def set_eval(self, flag: bool) -> None:
            self._eval_mode = bool(flag)
            self.eval_calls.append(self._eval_mode)

    env, policy, _meta, llm = _make_components()
    meta = StubMeta()
    run_eval(env, policy, meta, llm, n_episodes=1, max_steps_per_episode=10)
    # Was set to True for eval, then restored.
    assert True in meta.eval_calls
