"""Unit tests for the multi-agent PPO actor-critic."""

from __future__ import annotations

import numpy as np
import torch

from src.envs import EnvObservation
from src.policies import PPOPolicy
from src.policies.base import PolicyContext


def _make_ctx(obs_dim: int = 8, n_agents: int = 2, subgoal: dict[str, str] | None = None) -> PolicyContext:
    raw = {
        f"agent_{i}": np.arange(obs_dim, dtype=np.float32) + i for i in range(n_agents)
    }
    obs = EnvObservation(raw=raw, text="state", info={})
    return PolicyContext(
        obs=obs, current_subgoal=subgoal, steps_since_llm_call=0, episode_step=0
    )


def test_ppo_forward_shape() -> None:
    policy = PPOPolicy(obs_dim=8, action_dim=6, hidden_dim=32, n_layers=2)
    batch = torch.randn(5, 8)
    logits, value = policy.forward(batch)
    assert logits.shape == (5, 6)
    assert value.shape == (5,)


def test_ppo_act_returns_dict() -> None:
    policy = PPOPolicy(obs_dim=8, action_dim=6, hidden_dim=16, n_layers=1)
    ctx = _make_ctx()
    actions = policy.act(ctx)
    assert isinstance(actions, dict)
    assert set(actions.keys()) == set(ctx.obs.raw.keys())
    for aid, a in actions.items():
        assert isinstance(a, int)
        assert 0 <= a < 6
        cache = policy.last_step_cache[aid]
        assert "log_prob" in cache and "value" in cache
        assert isinstance(cache["log_prob"], float)
        assert isinstance(cache["value"], float)


def test_ppo_with_subgoal_input() -> None:
    sg_dim = 8
    policy = PPOPolicy(
        obs_dim=8,
        action_dim=6,
        hidden_dim=16,
        n_layers=1,
        use_subgoal=True,
        subgoal_dim=sg_dim,
    )

    # forward concatenates obs with subgoal one-hot of expected width.
    obs = torch.zeros(3, 8)
    sg = torch.zeros(3, sg_dim)
    sg[:, 0] = 1.0
    logits, value = policy.forward(obs, sg)
    assert logits.shape == (3, 6)
    assert value.shape == (3,)

    # `act` builds the subgoal one-hot from ctx.current_subgoal under the hood.
    ctx_with_sg = _make_ctx(subgoal={"agent_0": "go_to_onion", "agent_1": "pickup_onion"})
    actions = policy.act(ctx_with_sg)
    assert set(actions.keys()) == set(ctx_with_sg.obs.raw.keys())

    # `act` with no subgoal should still work — encoded as zero-vectors.
    ctx_no_sg = _make_ctx(subgoal=None)
    actions2 = policy.act(ctx_no_sg)
    assert set(actions2.keys()) == set(ctx_no_sg.obs.raw.keys())

    # Unknown subgoal name encodes as zeros (silent fallback).
    ctx_bad = _make_ctx(subgoal={"agent_0": "not_a_real_subgoal", "agent_1": "idle"})
    _ = policy.act(ctx_bad)


def test_ppo_evaluate_consistent() -> None:
    """`evaluate` log_prob must match the Categorical distribution at the same logits."""
    torch.manual_seed(0)
    policy = PPOPolicy(obs_dim=4, action_dim=3, hidden_dim=8, n_layers=1)
    obs = torch.randn(7, 4)
    actions = torch.randint(0, 3, (7,))

    logp, entropy, value = policy.evaluate(obs, actions)
    assert logp.shape == (7,)
    assert entropy.shape == (7,)
    assert value.shape == (7,)

    # Recompute manually to verify consistency.
    logits, _ = policy.forward(obs)
    expected = torch.distributions.Categorical(logits=logits).log_prob(actions)
    assert torch.allclose(logp, expected, atol=1e-6)
