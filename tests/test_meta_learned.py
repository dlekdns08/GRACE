"""Unit tests for the learned meta-policy MLP and feature builder."""

from __future__ import annotations

import numpy as np
import torch

from src.envs import DummyOvercookedEnv
from src.policies.base import PolicyContext
from src.policies.meta_learned import LearnedMetaPolicy, _featurize


def _make_ctx(env: DummyOvercookedEnv) -> PolicyContext:
    obs = env.reset()
    return PolicyContext(
        obs=obs,
        current_subgoal=None,
        steps_since_llm_call=0,
        episode_step=0,
    )


def test_meta_learned_forward_shape() -> None:
    """forward(feat) returns logits of shape [B, 2]."""
    torch.manual_seed(0)
    obs_dim = 8
    meta = LearnedMetaPolicy(obs_dim=obs_dim, hidden_dim=16)
    batch = torch.randn(7, obs_dim + 3)
    logits = meta(batch)
    assert logits.shape == (7, 2)
    # 1-D input also works (returns [2]).
    single = torch.randn(obs_dim + 3)
    logits1 = meta(single)
    assert logits1.shape == (2,)


def test_meta_learned_should_call_returns_bool() -> None:
    """`should_call_llm` returns a plain Python bool, not numpy/tensor."""
    torch.manual_seed(0)
    env = DummyOvercookedEnv()
    meta = LearnedMetaPolicy(obs_dim=env.obs_dim, hidden_dim=16)
    ctx = _make_ctx(env)
    decision = meta.should_call_llm(ctx)
    assert isinstance(decision, bool)
    # The cached state should be populated.
    assert meta.last_features is not None
    assert meta.last_logp is not None
    assert meta.last_decision == decision


def test_meta_learned_eval_mode_deterministic() -> None:
    """In eval mode, the same context yields the same decision deterministically."""
    torch.manual_seed(0)
    env = DummyOvercookedEnv()
    meta = LearnedMetaPolicy(obs_dim=env.obs_dim, hidden_dim=16)
    meta.set_eval(True)
    ctx = _make_ctx(env)

    decisions = [meta.should_call_llm(ctx) for _ in range(5)]
    assert len(set(decisions)) == 1, f"eval mode is not deterministic: {decisions}"


def test_featurize_dim() -> None:
    """`_featurize(ctx)` returns a 1-D float32 array of length obs_dim + 3."""
    env = DummyOvercookedEnv()
    ctx = _make_ctx(env)
    feat = _featurize(ctx)
    assert isinstance(feat, np.ndarray)
    assert feat.dtype == np.float32
    assert feat.shape == (env.obs_dim + 3,)


def test_featurize_subgoal_active_flag() -> None:
    """The subgoal-active scalar flips when a subgoal is set."""
    env = DummyOvercookedEnv()
    obs = env.reset()
    ctx_no = PolicyContext(obs=obs, current_subgoal=None, steps_since_llm_call=0, episode_step=0)
    ctx_yes = PolicyContext(
        obs=obs,
        current_subgoal={"agent_0": "go_to_onion", "agent_1": "go_to_onion"},
        steps_since_llm_call=0,
        episode_step=0,
    )
    feat_no = _featurize(ctx_no)
    feat_yes = _featurize(ctx_yes)
    # The subgoal-active flag is the first of the three trailing extras.
    assert feat_no[-3] == 0.0
    assert feat_yes[-3] == 1.0
