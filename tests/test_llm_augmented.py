"""Tests for the LLM-augmented PPO policy (DESIGN sections 3.3, 4.5)."""

from __future__ import annotations

import math

import numpy as np
import torch

from src.envs import DummyOvercookedEnv, EnvObservation
from src.llm import MockLLMClient
from src.policies import FixedKMetaPolicy, LLMAugmentedPPOPolicy
from src.policies.base import PolicyContext
from src.training import PPOTrainer, collect_rollout


def _make_ctx(
    obs_dim: int = 8,
    n_agents: int = 2,
    subgoal: dict[str, str] | None = None,
) -> PolicyContext:
    raw = {f"agent_{i}": np.arange(obs_dim, dtype=np.float32) + i for i in range(n_agents)}
    obs = EnvObservation(raw=raw, text="state", info={})
    return PolicyContext(
        obs=obs, current_subgoal=subgoal, steps_since_llm_call=0, episode_step=0
    )


def test_llm_augmented_forces_use_subgoal() -> None:
    policy = LLMAugmentedPPOPolicy(
        obs_dim=8, action_dim=6, hidden_dim=16, n_layers=1, subgoal_dim=8
    )
    assert policy.use_subgoal is True
    assert policy.subgoal_dim == 8


def test_llm_augmented_ignores_use_subgoal_override() -> None:
    """Caller-supplied use_subgoal=False is overridden — this policy is
    LLM-conditioned by definition."""
    policy = LLMAugmentedPPOPolicy(
        obs_dim=8,
        action_dim=6,
        hidden_dim=16,
        n_layers=1,
        subgoal_dim=8,
        use_subgoal=False,  # ignored
    )
    assert policy.use_subgoal is True


def test_subgoal_one_hot_shape() -> None:
    policy = LLMAugmentedPPOPolicy(
        obs_dim=8, action_dim=6, hidden_dim=16, n_layers=1, subgoal_dim=8
    )
    # Use only valid enum members from src.training.rollout.SUBGOAL_TO_IDX.
    ctx = _make_ctx(subgoal={"agent_0": "deliver_onion_to_pot", "agent_1": "wait_for_cook"})
    actions = policy.act(ctx)
    assert set(actions.keys()) == {"agent_0", "agent_1"}
    for aid, a in actions.items():
        assert isinstance(a, int)
        assert 0 <= a < 6
        cache = policy.last_step_cache[aid]
        assert isinstance(cache["log_prob"], float)
        assert isinstance(cache["value"], float)


def test_unknown_subgoal_falls_back_to_zeros() -> None:
    policy = LLMAugmentedPPOPolicy(
        obs_dim=8, action_dim=6, hidden_dim=16, n_layers=1, subgoal_dim=8
    )
    # "go_to_pot" is NOT in SUBGOAL_TO_IDX → should encode as zeros silently.
    ctx = _make_ctx(subgoal={"agent_0": "go_to_pot", "agent_1": "not_a_real_subgoal"})
    actions = policy.act(ctx)
    assert set(actions.keys()) == {"agent_0", "agent_1"}


def test_evaluate_with_subgoal() -> None:
    """End-to-end: rollout with valid subgoals → PPO update → finite metrics."""
    torch.manual_seed(0)
    env = DummyOvercookedEnv()
    policy = LLMAugmentedPPOPolicy(
        obs_dim=env.obs_dim,
        action_dim=env.action_space_size,
        hidden_dim=16,
        n_layers=1,
        n_epochs=2,
        minibatch_size=32,
        subgoal_dim=8,
    )
    meta = FixedKMetaPolicy(k=4)
    llm = MockLLMClient(
        [
            '{"agent_0": "go_to_onion", "agent_1": "go_to_onion"}',
            '{"agent_0": "deliver_onion_to_pot", "agent_1": "pickup_dish"}',
        ]
    )

    batch = collect_rollout(env, policy, meta, llm, n_steps=128)

    # At least some transitions must carry a non-None subgoal (the meta-policy
    # called LLM on step 0, so all subsequent transitions in that episode see one).
    has_subgoal = any(t.subgoal is not None for t in batch.transitions)
    assert has_subgoal, "Expected at least one transition with a populated subgoal"

    has_subgoal_oh = any(
        t.subgoal_oh is not None and any(v.sum() > 0 for v in t.subgoal_oh.values())
        for t in batch.transitions
    )
    assert has_subgoal_oh, "Expected at least one non-zero subgoal one-hot"

    trainer_cfg = {
        "gamma": 0.99,
        "gae_lambda": 0.95,
        "clip_range": 0.2,
        "value_coef": 0.5,
        "entropy_coef": 0.01,
        "n_epochs": 2,
        "minibatch_size": 32,
        "max_grad_norm": 0.5,
        "learning_rate": 1e-3,
    }
    trainer = PPOTrainer(policy, trainer_cfg)
    metrics = trainer.update(batch)

    expected = {"policy_loss", "value_loss", "entropy", "approx_kl", "clip_frac", "n_samples"}
    assert expected.issubset(metrics.keys())
    for k in ("policy_loss", "value_loss", "entropy", "approx_kl", "clip_frac"):
        assert math.isfinite(metrics[k]), f"non-finite metric {k}={metrics[k]}"
