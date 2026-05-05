"""Unit tests for the heuristic meta-policies (DESIGN section 4.5)."""

from __future__ import annotations

import numpy as np
import torch

from src.envs import EnvObservation
from src.policies import (
    AlwaysCallMetaPolicy,
    EntropyMetaPolicy,
    FixedKMetaPolicy,
    NeverCallMetaPolicy,
)
from src.policies.base import Policy, PolicyContext


# --------------------------------------------------------------------------- helpers
def _make_ctx(step: int, n_agents: int = 2, obs_dim: int = 8) -> PolicyContext:
    raw = {f"agent_{i}": np.zeros(obs_dim, dtype=np.float32) for i in range(n_agents)}
    obs = EnvObservation(raw=raw, text="state", info={})
    return PolicyContext(
        obs=obs, current_subgoal=None, steps_since_llm_call=0, episode_step=step
    )


class _MockHighEntropyPolicy(Policy):
    """Returns uniform logits → maximum entropy."""

    def __init__(self, n_agents: int = 2, action_dim: int = 6) -> None:
        self.n_agents = n_agents
        self.action_dim = action_dim

    def act(self, ctx: PolicyContext) -> dict[str, int]:  # pragma: no cover - unused
        return {f"agent_{i}": 0 for i in range(self.n_agents)}

    def get_logits(self, ctx: PolicyContext) -> torch.Tensor:
        return torch.zeros(self.n_agents, self.action_dim)


class _MockLowEntropyPolicy(Policy):
    """Returns sharp (one-hot-ish) logits → entropy ~ 0."""

    def __init__(self, n_agents: int = 2, action_dim: int = 6) -> None:
        self.n_agents = n_agents
        self.action_dim = action_dim

    def act(self, ctx: PolicyContext) -> dict[str, int]:  # pragma: no cover - unused
        return {f"agent_{i}": 0 for i in range(self.n_agents)}

    def get_logits(self, ctx: PolicyContext) -> torch.Tensor:
        logits = torch.full((self.n_agents, self.action_dim), -50.0)
        logits[:, 0] = 50.0
        return logits


# ---------------------------------------------------------------------------- tests
def test_fixed_k_calls_at_correct_intervals() -> None:
    meta = FixedKMetaPolicy(k=10)
    decisions = [meta.should_call_llm(_make_ctx(step=i)) for i in range(30)]
    # Calls at step 0, 10, 20.
    assert sum(decisions) == 3
    assert decisions[0] is True
    assert decisions[10] is True
    assert decisions[20] is True
    assert decisions[1] is False
    assert decisions[15] is False


def test_fixed_k_rejects_non_positive() -> None:
    import pytest

    with pytest.raises(ValueError):
        FixedKMetaPolicy(k=0)
    with pytest.raises(ValueError):
        FixedKMetaPolicy(k=-3)


def test_never_meta() -> None:
    meta = NeverCallMetaPolicy()
    for i in range(50):
        assert meta.should_call_llm(_make_ctx(step=i)) is False
    assert meta.last_decision is False


def test_always_meta() -> None:
    meta = AlwaysCallMetaPolicy()
    for i in range(50):
        assert meta.should_call_llm(_make_ctx(step=i)) is True
    assert meta.last_decision is True


def test_entropy_meta_respects_cooldown() -> None:
    meta = EntropyMetaPolicy(threshold=0.1, min_steps_between=5)
    meta.attach(_MockHighEntropyPolicy())

    # Step 0: cooldown sentinel allows call, entropy >> threshold → True.
    assert meta.should_call_llm(_make_ctx(step=0)) is True
    assert meta.last_decision is True
    # Step 1: still inside the 5-step cooldown → False even though entropy is high.
    assert meta.should_call_llm(_make_ctx(step=1)) is False
    assert meta.should_call_llm(_make_ctx(step=2)) is False
    assert meta.should_call_llm(_make_ctx(step=3)) is False
    assert meta.should_call_llm(_make_ctx(step=4)) is False
    # Step 5: exactly `min_steps_between` away → cooldown released → True.
    assert meta.should_call_llm(_make_ctx(step=5)) is True


def test_entropy_meta_below_threshold() -> None:
    meta = EntropyMetaPolicy(threshold=0.5, min_steps_between=2)
    meta.attach(_MockLowEntropyPolicy())

    # Sharp logits → entropy is essentially zero, well below 0.5.
    for i in range(20):
        assert meta.should_call_llm(_make_ctx(step=i)) is False
    assert meta.last_entropy is not None
    assert meta.last_entropy < 0.5


def test_entropy_meta_no_attach_no_call() -> None:
    meta = EntropyMetaPolicy(threshold=0.0, min_steps_between=0)
    # No `attach()` was called → meta-policy is silent regardless of step.
    for i in range(10):
        assert meta.should_call_llm(_make_ctx(step=i)) is False


def test_entropy_meta_reset_clears_cooldown() -> None:
    meta = EntropyMetaPolicy(threshold=0.1, min_steps_between=5)
    meta.attach(_MockHighEntropyPolicy())
    assert meta.should_call_llm(_make_ctx(step=0)) is True
    # After reset, even step 0 should fire again (cooldown sentinel restored).
    meta.reset()
    assert meta.last_decision is False
    assert meta.last_entropy is None
    assert meta.should_call_llm(_make_ctx(step=0)) is True
