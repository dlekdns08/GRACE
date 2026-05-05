"""Unit tests for `collect_rollout` against the in-memory dummy env."""

from __future__ import annotations

import numpy as np

from src.envs import DummyOvercookedEnv
from src.llm import MockLLMClient
from src.policies import PPOPolicy
from src.policies.base import MetaPolicy, PolicyContext
from src.training import RolloutBatch, collect_rollout, subgoal_to_onehot


class _CallEveryStep(MetaPolicy):
    def should_call_llm(self, ctx: PolicyContext) -> bool:
        self.last_decision = True
        return True


class _NeverCall(MetaPolicy):
    def should_call_llm(self, ctx: PolicyContext) -> bool:
        self.last_decision = False
        return False


_RESPONSES = [
    '{"agent_0": "go_to_onion", "agent_1": "go_to_onion"}',
    '{"agent_0": "deliver_onion_to_pot", "agent_1": "pickup_dish"}',
]


def test_subgoal_to_onehot_basic() -> None:
    """One-hot encoding sanity: known names hit the right index, unknowns are zero."""
    oh = subgoal_to_onehot("go_to_onion")
    assert oh.shape == (8,)
    assert int(oh.argmax()) == 0
    assert oh.sum() == 1.0

    oh2 = subgoal_to_onehot("idle")
    assert int(oh2.argmax()) == 7

    oh_none = subgoal_to_onehot(None)
    assert oh_none.shape == (8,)
    assert oh_none.sum() == 0.0

    oh_bad = subgoal_to_onehot("not_a_subgoal")
    assert oh_bad.sum() == 0.0


def test_collect_rollout_dummy_env() -> None:
    """End-to-end smoke: 100 steps complete and produce a RolloutBatch."""
    env = DummyOvercookedEnv()
    policy = PPOPolicy(
        obs_dim=env.obs_dim, action_dim=env.action_space_size, hidden_dim=16, n_layers=1
    )
    meta = _NeverCall()
    llm = MockLLMClient(_RESPONSES)

    batch = collect_rollout(env, policy, meta, llm, n_steps=100)

    assert isinstance(batch, RolloutBatch)
    assert len(batch.transitions) == 100
    # Never-call meta should yield zero LLM calls.
    assert batch.n_llm_calls == 0

    # Every transition has all the fields populated.
    for tr in batch.transitions:
        assert set(tr.obs_raw.keys()) == set(env.agent_ids)
        assert set(tr.actions.keys()) == set(env.agent_ids)
        assert set(tr.rewards.keys()) == set(env.agent_ids)
        assert tr.llm_called is False
        for aid in env.agent_ids:
            assert isinstance(tr.actions[aid], int)
            assert isinstance(tr.log_probs[aid], float)
            assert isinstance(tr.values[aid], float)


def test_collect_rollout_calls_llm() -> None:
    """A meta-policy that always returns True triggers an LLM call every step."""
    env = DummyOvercookedEnv()
    policy = PPOPolicy(
        obs_dim=env.obs_dim, action_dim=env.action_space_size, hidden_dim=16, n_layers=1
    )
    meta = _CallEveryStep()
    llm = MockLLMClient(_RESPONSES)

    batch = collect_rollout(env, policy, meta, llm, n_steps=20)

    assert len(batch.transitions) == 20
    assert batch.n_llm_calls == 20
    # Every transition should record llm_called=True.
    assert all(tr.llm_called for tr in batch.transitions)
    # The mock LLM returned valid subgoals, so subgoals should be populated.
    assert all(tr.subgoal is not None for tr in batch.transitions)
    for tr in batch.transitions:
        assert tr.subgoal_oh is not None
        for aid in env.agent_ids:
            arr = tr.subgoal_oh[aid]
            assert isinstance(arr, np.ndarray)
            assert arr.shape == (8,)
