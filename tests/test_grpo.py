"""Unit tests for GRPO trainer and the meta-rollout collector."""

from __future__ import annotations

import math

import numpy as np
import torch

from src.envs import DummyOvercookedEnv
from src.llm import MockLLMClient
from src.policies import PPOPolicy
from src.policies.meta_learned import LearnedMetaPolicy
from src.training.grpo_trainer import (
    GRPOTrainer,
    MetaDecision,
    MetaRollout,
    collect_meta_rollout,
)


def _make_meta(obs_dim: int = 8) -> LearnedMetaPolicy:
    torch.manual_seed(0)
    return LearnedMetaPolicy(obs_dim=obs_dim, hidden_dim=16)


def _fake_decisions(rng: np.random.Generator, n: int, dim: int) -> list[MetaDecision]:
    return [
        MetaDecision(
            features=rng.standard_normal(dim).astype(np.float32),
            action=int(rng.integers(0, 2)),
            logp=0.0,
        )
        for _ in range(n)
    ]


def test_grpo_update_runs() -> None:
    """A fabricated group of MetaRollouts drives a finite update; meta params change."""
    torch.manual_seed(0)
    obs_dim = 8
    meta = _make_meta(obs_dim=obs_dim)
    trainer = GRPOTrainer(
        meta_policy=meta,
        learning_rate=1e-2,
        call_cost=0.01,
        kl_coef=0.02,
        group_size=4,
    )

    rng = np.random.default_rng(42)
    feat_dim = obs_dim + 3
    group = [
        MetaRollout(
            decisions=_fake_decisions(rng, n=8, dim=feat_dim),
            total_reward=float(rng.uniform(0.0, 5.0)),
            n_llm_calls=int(rng.integers(0, 6)),
        )
        for _ in range(4)
    ]

    before = {name: p.detach().clone() for name, p in meta.named_parameters()}
    metrics = trainer.update(group)

    expected_keys = {
        "policy_loss",
        "kl",
        "mean_R",
        "std_R",
        "mean_calls",
        "n_decisions",
        "n_groups",
    }
    assert expected_keys.issubset(set(metrics.keys()))
    for k in ("policy_loss", "kl", "mean_R", "std_R", "mean_calls"):
        assert math.isfinite(metrics[k]), f"non-finite metric: {k}={metrics[k]}"
    assert metrics["n_decisions"] == 32.0
    assert metrics["n_groups"] == 4.0

    # At least one parameter must have moved.
    moved = any(
        not torch.allclose(p.detach(), before[name])
        for name, p in meta.named_parameters()
    )
    assert moved, "GRPO update did not change any meta-policy parameters"


def test_grpo_empty_group_is_noop() -> None:
    """Empty group returns zero metrics without crashing."""
    meta = _make_meta()
    trainer = GRPOTrainer(meta_policy=meta)
    metrics = trainer.update([])
    assert metrics["n_groups"] == 0.0
    assert metrics["policy_loss"] == 0.0


def test_grpo_update_reference_refreshes_snapshot() -> None:
    """update_reference replaces the KL reference with current parameters."""
    meta = _make_meta()
    trainer = GRPOTrainer(meta_policy=meta, kl_coef=0.0)
    # Mutate the policy parameters by hand.
    with torch.no_grad():
        for p in meta.parameters():
            p.add_(0.5)
    trainer.update_reference()
    feat = torch.zeros(1, meta.input_dim)
    with torch.no_grad():
        a = meta.net(feat)
        b = trainer._ref(feat)
    assert torch.allclose(a, b)


def test_collect_meta_rollout_records_all_decisions() -> None:
    """`collect_meta_rollout` records exactly one decision per env step."""
    env = DummyOvercookedEnv(max_steps=20)
    policy = PPOPolicy(
        obs_dim=env.obs_dim,
        action_dim=env.action_space_size,
        hidden_dim=16,
        n_layers=1,
    )
    meta = _make_meta(obs_dim=env.obs_dim)
    llm = MockLLMClient(['{"agent_0": "go_to_onion", "agent_1": "go_to_onion"}'])

    rollout = collect_meta_rollout(
        env=env,
        action_policy=policy,
        meta_policy=meta,
        llm_client=llm,
        max_steps=15,
    )

    # The episode either ran to max_steps (15) or terminated earlier; in both
    # cases the number of decisions == number of env steps that actually ran.
    assert len(rollout.decisions) > 0
    assert len(rollout.decisions) <= 15
    # Every decision has features of the right size and a valid action.
    for dec in rollout.decisions:
        assert isinstance(dec.features, np.ndarray)
        assert dec.features.shape == (env.obs_dim + 3,)
        assert dec.action in (0, 1)
    # n_llm_calls equals the number of decisions where action == 1.
    n_call_decisions = sum(1 for dec in rollout.decisions if dec.action == 1)
    assert rollout.n_llm_calls == n_call_decisions


def test_collect_meta_rollout_records_skips_too() -> None:
    """When the meta-policy never calls the LLM, decisions still cover every step."""
    env = DummyOvercookedEnv(max_steps=10)
    policy = PPOPolicy(
        obs_dim=env.obs_dim, action_dim=env.action_space_size, hidden_dim=16, n_layers=1
    )
    meta = _make_meta(obs_dim=env.obs_dim)

    # Force the policy into a state where it always picks "skip" by zeroing
    # the policy head and setting bias so action 0 wins by a wide margin.
    with torch.no_grad():
        last = meta.net[-1]
        last.weight.zero_()
        last.bias.copy_(torch.tensor([10.0, -10.0]))
    meta.set_eval(True)

    llm = MockLLMClient(['{"agent_0": "idle", "agent_1": "idle"}'])
    rollout = collect_meta_rollout(
        env=env,
        action_policy=policy,
        meta_policy=meta,
        llm_client=llm,
        max_steps=8,
    )

    assert rollout.n_llm_calls == 0
    assert len(rollout.decisions) > 0
    assert all(dec.action == 0 for dec in rollout.decisions)
