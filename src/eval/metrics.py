"""Pure metric helpers over rollout/eval logs (DESIGN section 6).

These functions consume the parquet schemas written by
:class:`src.utils.logging.RolloutLogger` and the eval runner: an
``episodes`` frame (one row per episode, columns ``return``, ``length``,
``soup_count``, ``llm_calls``, ``cached_calls``), a ``transitions``
frame (one row per env step, including ``llm_called``), and an
``llm_calls`` frame (one row per actual LLM invocation, with ``cached``
and ``step``).

All functions are deliberately stateless and side-effect-free so they can
be reused both inside :mod:`scripts.eval` and from notebooks.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(slots=True)
class EpisodeSummary:
    """Per-episode aggregate row produced by :func:`run_eval`."""

    episode: int
    return_: float
    length: int
    soup_count: int
    llm_calls: int
    cached_calls: int


# --------------------------------------------------------------------- aggregation
def aggregate_episodes(episodes: pd.DataFrame) -> dict[str, float]:
    """Aggregate an ``episodes`` DataFrame into scalar summary stats.

    Accepts either the parquet-on-disk schema (``return`` column) or the
    in-memory eval-runner schema (``return_`` column). Returns a dict with
    NaN-safe floats and ``n_episodes`` as an integer count.
    """
    n = int(len(episodes))
    if n == 0:
        return {
            "mean_return": 0.0,
            "std_return": 0.0,
            "mean_soup_count": 0.0,
            "mean_llm_calls": 0.0,
            "mean_cached_calls": 0.0,
            "n_episodes": 0,
        }

    # Tolerate the two naming conventions in use across the codebase.
    if "return_" in episodes.columns:
        ret = episodes["return_"].to_numpy(dtype=float)
    elif "return" in episodes.columns:
        ret = episodes["return"].to_numpy(dtype=float)
    else:
        ret = np.zeros(n, dtype=float)

    soup = episodes.get("soup_count", pd.Series([0.0] * n)).to_numpy(dtype=float)
    calls = episodes.get("llm_calls", pd.Series([0.0] * n)).to_numpy(dtype=float)
    cached = episodes.get("cached_calls", pd.Series([0.0] * n)).to_numpy(dtype=float)

    # ddof=0 to match numpy's default and avoid NaN for n_episodes == 1.
    return {
        "mean_return": float(ret.mean()),
        "std_return": float(ret.std(ddof=0)),
        "mean_soup_count": float(soup.mean()),
        "mean_llm_calls": float(calls.mean()),
        "mean_cached_calls": float(cached.mean()),
        "n_episodes": n,
    }


# ----------------------------------------------------------------- per-episode call counts
def llm_calls_per_episode(transitions: pd.DataFrame) -> pd.Series:
    """Count rows with ``llm_called == True`` grouped by ``episode``.

    Returns an int Series indexed by episode id. If ``transitions`` is
    empty or lacks the expected columns, returns an empty Series.
    """
    if transitions.empty or "llm_called" not in transitions.columns:
        return pd.Series([], name="llm_calls", dtype=int)
    if "episode" not in transitions.columns:
        # Treat the whole frame as one episode if no grouping column is present.
        return pd.Series(
            [int(transitions["llm_called"].astype(bool).sum())],
            index=pd.Index([0], name="episode"),
            name="llm_calls",
        )
    called = transitions["llm_called"].astype(bool)
    out = (
        transitions.assign(_called=called)
        .groupby("episode")["_called"]
        .sum()
        .astype(int)
    )
    out.name = "llm_calls"
    return out


# --------------------------------------------------------------------- cache hit rate
def cached_hit_rate(llm_calls: pd.DataFrame) -> float:
    """Fraction of rows in ``llm_calls`` whose ``cached`` flag is True."""
    if llm_calls.empty or "cached" not in llm_calls.columns:
        return 0.0
    flags = llm_calls["cached"].astype(bool)
    if len(flags) == 0:
        return 0.0
    return float(flags.sum()) / float(len(flags))


# ----------------------------------------------------------------- call-step distribution
def call_step_distribution(
    llm_calls: pd.DataFrame, max_steps: int = 400, n_bins: int = 20
) -> np.ndarray:
    """Histogram of LLM call timing within an episode.

    Each row in ``llm_calls`` contributes its ``step`` value (clipped to
    ``[0, max_steps]``) to a histogram with ``n_bins`` equal-width bins
    spanning ``[0, max_steps]``. Returns the bin counts as a 1-D
    ``np.ndarray`` of length ``n_bins``.
    """
    if n_bins <= 0:
        raise ValueError("n_bins must be positive")
    if max_steps <= 0:
        raise ValueError("max_steps must be positive")

    if llm_calls.empty or "step" not in llm_calls.columns:
        return np.zeros((n_bins,), dtype=int)

    steps = np.clip(llm_calls["step"].to_numpy(dtype=float), 0.0, float(max_steps))
    edges = np.linspace(0.0, float(max_steps), n_bins + 1)
    hist, _ = np.histogram(steps, bins=edges)
    return hist.astype(int)
