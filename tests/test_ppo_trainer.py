"""End-to-end test that PPOTrainer.update runs and changes parameters."""

from __future__ import annotations

import math

import torch

from src.envs import DummyOvercookedEnv
from src.llm import MockLLMClient
from src.policies import PPOPolicy
from src.policies.base import MetaPolicy, PolicyContext
from src.training import PPOTrainer, collect_rollout


class _NeverCall(MetaPolicy):
    def should_call_llm(self, ctx: PolicyContext) -> bool:
        self.last_decision = False
        return False


def test_ppo_update_runs() -> None:
    torch.manual_seed(0)
    env = DummyOvercookedEnv()
    policy = PPOPolicy(
        obs_dim=env.obs_dim,
        action_dim=env.action_space_size,
        hidden_dim=16,
        n_layers=1,
        n_epochs=2,
        minibatch_size=32,
    )
    meta = _NeverCall()
    llm = MockLLMClient(['{"agent_0": "idle", "agent_1": "idle"}'])

    batch = collect_rollout(env, policy, meta, llm, n_steps=128)

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

    # Snapshot params before the update.
    before = {name: p.detach().clone() for name, p in policy.named_parameters()}

    metrics = trainer.update(batch)

    # All metric values are finite and present.
    expected_keys = {"policy_loss", "value_loss", "entropy", "approx_kl", "clip_frac", "n_samples"}
    assert expected_keys.issubset(set(metrics.keys()))
    for k in ("policy_loss", "value_loss", "entropy", "approx_kl", "clip_frac"):
        assert math.isfinite(metrics[k]), f"non-finite metric: {k}={metrics[k]}"

    # At least one parameter must have moved.
    moved = False
    for name, p in policy.named_parameters():
        if not torch.allclose(p.detach(), before[name]):
            moved = True
            break
    assert moved, "PPO update did not change any policy parameters"
