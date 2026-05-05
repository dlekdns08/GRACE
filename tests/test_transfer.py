"""Smoke test for :func:`src.eval.transfer.evaluate_transfer` (Phase 11).

We can't really exercise cross-layout zero-shot quality without the
actual Carroll Overcooked layouts, so this test focuses on the *plumbing*:
given a custom ``env_factory`` that returns ``DummyOvercookedEnv`` for
every requested layout, the function should return a well-shaped frame
without crashing.
"""

from __future__ import annotations

import pandas as pd

from src.envs import DummyOvercookedEnv, OvercookedEnv
from src.eval.transfer import evaluate_transfer
from src.llm.mock import MockLLMClient
from src.policies import FixedKMetaPolicy, PPOPolicy


def _dummy_factory(_layout: str) -> OvercookedEnv:
    """Return a fresh DummyOvercookedEnv regardless of layout name."""
    return DummyOvercookedEnv(max_steps=10)


def test_evaluate_transfer_dummy(tmp_path):
    """Exercise the transfer pipeline end-to-end with dummy envs."""
    test_layouts = ["layout_a", "layout_b"]

    env = DummyOvercookedEnv(max_steps=10)

    def policy_ctor() -> PPOPolicy:
        return PPOPolicy(obs_dim=env.obs_dim, action_dim=env.action_space_size)

    meta = FixedKMetaPolicy(k=3)
    llm = MockLLMClient(
        responses=[
            '{"agent_0": "go_to_onion", "agent_1": "go_to_onion"}',
            '{"agent_0": "deliver_onion_to_pot", "agent_1": "pickup_dish"}',
        ]
    )

    # Use a non-existent checkpoint path: evaluate_transfer should warn
    # and proceed with fresh weights.
    fake_ckpt = tmp_path / "policy.pt"

    df = evaluate_transfer(
        train_layout="train_layout",
        test_layouts=test_layouts,
        policy_ctor=policy_ctor,
        checkpoint_path=fake_ckpt,
        meta_policy=meta,
        llm_client=llm,
        n_episodes=2,
        env_factory=_dummy_factory,
    )

    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == [
        "train_layout",
        "test_layout",
        "mean_return",
        "mean_soup_count",
        "mean_llm_calls",
        "n_episodes",
    ]
    # One row per requested test layout.
    assert len(df) == len(test_layouts)
    assert df["train_layout"].tolist() == ["train_layout"] * len(test_layouts)
    assert df["test_layout"].tolist() == test_layouts
    # n_episodes column reflects the per-layout episode count.
    assert (df["n_episodes"] == 2).all()
    # Numeric columns are finite floats.
    for col in ("mean_return", "mean_soup_count", "mean_llm_calls"):
        assert df[col].dtype.kind == "f"
        assert df[col].notna().all()
