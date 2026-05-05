"""Eval runner — execute N evaluation episodes in deterministic mode.

The runner is intentionally a thin wrapper over
:func:`src.training.rollout.collect_rollout`. It loops one episode at a
time so that:

* each episode gets its own ``env.reset(seed=seed_base + i)`` for
  determinism and reproducibility;
* the action policy switches to argmax (no exploration noise) and the
  meta-policy switches to its deterministic decision branch (if it
  exposes a ``set_eval`` hook);
* the runner can return one row per episode with the same column layout
  as :class:`src.eval.metrics.EpisodeSummary`.
"""

from __future__ import annotations

from contextlib import suppress
from typing import Any

import pandas as pd

from src.envs import OvercookedEnv
from src.llm.client import LLMClient
from src.policies.base import MetaPolicy, Policy
from src.training.rollout import collect_rollout


def _set_policy_eval(policy: Policy) -> dict[str, Any]:
    """Switch the action policy into deterministic eval mode.

    Returns a dict of restore actions to undo on exit.
    """
    restore: dict[str, Any] = {}

    # torch.nn.Module.eval() flips dropout/batchnorm — harmless if absent.
    eval_fn = getattr(policy, "eval", None)
    train_state: bool | None = None
    if callable(eval_fn) and hasattr(policy, "training"):
        train_state = bool(getattr(policy, "training"))
        with suppress(Exception):
            eval_fn()
            restore["train_state"] = train_state

    # PPOPolicy specific: turn off action sampling so we get argmax.
    set_sampling = getattr(policy, "set_sampling", None)
    if callable(set_sampling):
        prev_sampling = bool(getattr(policy, "_sampling", True))
        with suppress(Exception):
            set_sampling(False)
            restore["sampling"] = prev_sampling

    return restore


def _restore_policy(policy: Policy, restore: dict[str, Any]) -> None:
    if "train_state" in restore and restore["train_state"]:
        train_fn = getattr(policy, "train", None)
        if callable(train_fn):
            with suppress(Exception):
                train_fn(True)
    if "sampling" in restore:
        set_sampling = getattr(policy, "set_sampling", None)
        if callable(set_sampling):
            with suppress(Exception):
                set_sampling(bool(restore["sampling"]))


def _set_meta_eval(meta_policy: MetaPolicy) -> bool | None:
    """Try to flip the meta-policy into eval mode.

    Returns the previous flag (or ``None`` if the meta-policy doesn't
    expose ``set_eval``) for later restoration.
    """
    set_eval = getattr(meta_policy, "set_eval", None)
    if not callable(set_eval):
        return None
    prev = bool(getattr(meta_policy, "_eval_mode", False))
    with suppress(Exception):
        set_eval(True)
    return prev


def _restore_meta(meta_policy: MetaPolicy, prev: bool | None) -> None:
    if prev is None:
        return
    set_eval = getattr(meta_policy, "set_eval", None)
    if callable(set_eval):
        with suppress(Exception):
            set_eval(prev)


def _run_one_episode(
    env: OvercookedEnv,
    policy: Policy,
    meta_policy: MetaPolicy,
    llm_client: LLMClient,
    max_steps: int,
    episode_id: int,
    seed: int,
) -> dict[str, Any]:
    """Roll one episode under eval conditions and return a summary row.

    The trick: we ask :func:`collect_rollout` for ``max_steps`` steps
    starting from a seeded reset. Whether the env terminates inside that
    window or is truncated at the boundary, we report the first episode
    only. ``collect_rollout`` already calls ``env.reset()`` internally,
    so we seed via :meth:`env.reset` *before* invoking it; the rollout's
    own reset will re-seed deterministically with the same seed only if
    the env supports it. To make the seeding airtight, we monkey-patch
    nothing — instead we wrap the env's ``reset`` for a single call.
    """
    # Force the next env.reset() invoked by collect_rollout to use our seed
    # exactly once. We do this by calling reset ourselves first and then
    # letting collect_rollout do its own reset; for our DummyOvercookedEnv
    # this is a no-op since reset is deterministic, but for stochastic envs
    # we patch reset's default seed.
    env.reset(seed=seed)

    original_reset = env.reset

    def _seeded_reset(seed_arg: int | None = None) -> Any:
        # First call after install: use our seed regardless of what
        # collect_rollout passed. Then restore the original behaviour.
        env.reset = original_reset  # type: ignore[method-assign]
        return original_reset(seed=seed if seed_arg is None else seed_arg)

    env.reset = _seeded_reset  # type: ignore[method-assign]

    try:
        batch = collect_rollout(
            env=env,
            policy=policy,
            meta_policy=meta_policy,
            llm_client=llm_client,
            n_steps=max_steps,
            logger=None,
            episode_id=episode_id,
            use_async_llm=False,
        )
    finally:
        env.reset = original_reset  # type: ignore[method-assign]

    # Pull the first completed episode's stats; if the env never
    # terminated within max_steps, synthesize a row from the partial
    # transitions we collected.
    if batch.episode_returns:
        ep_return = float(batch.episode_returns[0])
        ep_length = int(batch.episode_lengths[0])
        soup_count = int(batch.soup_counts[0])
    else:
        ep_return = float(sum(sum(t.rewards.values()) for t in batch.transitions))
        ep_length = int(len(batch.transitions))
        soup_count = 0

    # LLM-call accounting from the rollout batch counts the transitions
    # that produced an actual call this rollout — for a single-episode
    # rollout this is exactly the per-episode count.
    llm_calls = int(batch.n_llm_calls)
    cached_calls = int(batch.n_cached_calls)

    return {
        "episode": int(episode_id),
        "return_": ep_return,
        "length": ep_length,
        "soup_count": soup_count,
        "llm_calls": llm_calls,
        "cached_calls": cached_calls,
    }


def run_eval(
    env: OvercookedEnv,
    policy: Policy,
    meta_policy: MetaPolicy,
    llm_client: LLMClient,
    n_episodes: int = 20,
    max_steps_per_episode: int = 400,
    seed_base: int = 1000,
) -> pd.DataFrame:
    """Run ``n_episodes`` eval episodes and return one row per episode.

    Columns: ``episode, return_, length, soup_count, llm_calls,
    cached_calls`` — matching :class:`EpisodeSummary`.
    """
    if n_episodes <= 0:
        raise ValueError("n_episodes must be positive")
    if max_steps_per_episode <= 0:
        raise ValueError("max_steps_per_episode must be positive")

    restore_policy = _set_policy_eval(policy)
    prev_meta_eval = _set_meta_eval(meta_policy)

    rows: list[dict[str, Any]] = []
    try:
        for i in range(n_episodes):
            row = _run_one_episode(
                env=env,
                policy=policy,
                meta_policy=meta_policy,
                llm_client=llm_client,
                max_steps=max_steps_per_episode,
                episode_id=i,
                seed=seed_base + i,
            )
            rows.append(row)
    finally:
        _restore_policy(policy, restore_policy)
        _restore_meta(meta_policy, prev_meta_eval)

    return pd.DataFrame(rows, columns=[
        "episode",
        "return_",
        "length",
        "soup_count",
        "llm_calls",
        "cached_calls",
    ])
