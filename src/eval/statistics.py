"""Statistical utilities for cross-seed comparisons (DESIGN section 6).

These helpers operate on the per-run summary frames produced by the
sweep / eval pipeline. They live as a separate module from
:mod:`src.eval.metrics` because they are cross-run rather than
per-run aggregations and pull in :mod:`scipy.stats`.

Conventions
-----------
- ``a`` / ``b`` are 1-D arrays of paired observations (one entry per
  matched seed). The length of ``a`` and ``b`` must agree.
- Differences are always defined as ``a - b`` so the convention
  ``a = treatment, b = baseline`` yields positive numbers when the
  treatment helps.
- Confidence intervals use the percentile bootstrap (no bias-correction
  beyond the simple percentile method, which is sufficient at
  ``n_resamples >= 10_000`` for our use case).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd


@dataclass(slots=True)
class ComparisonResult:
    """Outcome of a paired comparison between two conditions.

    Attributes
    ----------
    method:
        Either ``"paired_bootstrap"`` or ``"wilcoxon"``.
    n_pairs:
        Number of seed-matched pairs that went into the comparison.
    diff_mean:
        ``mean(a) - mean(b)``.
    ci_low, ci_high:
        Lower / upper bound of the confidence interval (paired
        bootstrap) — both ``nan`` for Wilcoxon.
    p_value:
        Two-sided Wilcoxon p-value (or ``None`` for the bootstrap
        result).
    """

    method: Literal["paired_bootstrap", "wilcoxon"]
    n_pairs: int
    diff_mean: float
    ci_low: float
    ci_high: float
    p_value: float | None


def _validate_pair(a: np.ndarray, b: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    a_arr = np.asarray(a, dtype=float).reshape(-1)
    b_arr = np.asarray(b, dtype=float).reshape(-1)
    if a_arr.shape != b_arr.shape:
        raise ValueError(
            f"Paired inputs must have matching shape; got {a_arr.shape} vs {b_arr.shape}"
        )
    if a_arr.size == 0:
        raise ValueError("Inputs must contain at least one paired observation.")
    return a_arr, b_arr


def paired_bootstrap_ci(
    a: np.ndarray,
    b: np.ndarray,
    n_resamples: int = 10_000,
    confidence: float = 0.95,
    seed: int = 0,
) -> ComparisonResult:
    """Percentile-bootstrap CI for the paired mean difference ``mean(a-b)``.

    Resamples the *pair indices* (so the seed-matching is preserved)
    ``n_resamples`` times and returns the percentile interval at the
    requested confidence level.
    """
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie strictly between 0 and 1.")
    if n_resamples <= 0:
        raise ValueError("n_resamples must be positive.")

    a_arr, b_arr = _validate_pair(a, b)
    n = a_arr.size
    diffs = a_arr - b_arr

    rng = np.random.default_rng(seed)
    idx = rng.integers(0, n, size=(n_resamples, n))
    boot = diffs[idx].mean(axis=1)

    alpha = 1.0 - confidence
    low = float(np.quantile(boot, alpha / 2.0))
    high = float(np.quantile(boot, 1.0 - alpha / 2.0))

    return ComparisonResult(
        method="paired_bootstrap",
        n_pairs=int(n),
        diff_mean=float(diffs.mean()),
        ci_low=low,
        ci_high=high,
        p_value=None,
    )


def wilcoxon_signed_rank(a: np.ndarray, b: np.ndarray) -> ComparisonResult:
    """Two-sided Wilcoxon signed-rank test for paired observations.

    Wraps :func:`scipy.stats.wilcoxon`. Pairs whose difference is
    exactly zero are handled by scipy's default ``zero_method='wilcox'``.
    """
    from scipy import stats

    a_arr, b_arr = _validate_pair(a, b)
    diffs = a_arr - b_arr

    if np.allclose(diffs, 0.0):
        # Scipy raises on all-zero diffs; report a degenerate but
        # well-defined result rather than letting it bubble up.
        return ComparisonResult(
            method="wilcoxon",
            n_pairs=int(a_arr.size),
            diff_mean=0.0,
            ci_low=float("nan"),
            ci_high=float("nan"),
            p_value=1.0,
        )

    res = stats.wilcoxon(a_arr, b_arr, alternative="two-sided")
    return ComparisonResult(
        method="wilcoxon",
        n_pairs=int(a_arr.size),
        diff_mean=float(diffs.mean()),
        ci_low=float("nan"),
        ci_high=float("nan"),
        p_value=float(res.pvalue),
    )


# ----------------------------------------------------------- Pareto frontier
def pareto_dominance(
    runs: pd.DataFrame,
    cost_col: str = "mean_llm_calls",
    perf_col: str = "mean_soup_count",
) -> pd.DataFrame:
    """Return the rows of ``runs`` that lie on the cost/perf Pareto frontier.

    A run ``i`` is *dominated* iff there exists another run ``j`` with
    ``cost[j] <= cost[i]`` and ``perf[j] >= perf[i]`` and at least one
    of those inequalities is strict. Only non-dominated rows are
    returned, preserving the original index order.
    """
    if runs.empty:
        return runs.copy()
    if cost_col not in runs.columns or perf_col not in runs.columns:
        raise KeyError(
            f"runs is missing required columns: need {cost_col!r} and {perf_col!r}"
        )

    cost = runs[cost_col].to_numpy(dtype=float)
    perf = runs[perf_col].to_numpy(dtype=float)
    n = len(runs)

    keep = np.ones(n, dtype=bool)
    for i in range(n):
        if not keep[i]:
            continue
        for j in range(n):
            if i == j:
                continue
            if cost[j] <= cost[i] and perf[j] >= perf[i] and (
                cost[j] < cost[i] or perf[j] > perf[i]
            ):
                keep[i] = False
                break

    return runs.iloc[keep].copy()


# ----------------------------------------------------------- meta-policy comparison
def compare_meta_policies(
    runs: pd.DataFrame,
    baseline: str = "fixed_k100",
    perf_col: str = "mean_soup_count",
    cost_col: str = "mean_llm_calls",
) -> pd.DataFrame:
    """Per non-baseline meta-policy, return paired-bootstrap CIs vs baseline.

    The input frame is expected to have at least the columns
    ``meta``, ``seed``, ``perf_col``, ``cost_col``. Pairs are matched
    by seed: if a meta-policy and the baseline both have entries for
    seed ``s``, that pair contributes one observation. Metas with no
    overlapping seeds with the baseline are skipped.
    """
    required = {"meta", "seed", perf_col, cost_col}
    missing = required - set(runs.columns)
    if missing:
        raise KeyError(f"runs is missing columns: {sorted(missing)}")

    if baseline not in set(runs["meta"]):
        return pd.DataFrame(
            columns=[
                "meta",
                "n_seeds",
                "perf_diff_mean",
                "perf_ci_low",
                "perf_ci_high",
                "cost_diff_mean",
                "cost_ci_low",
                "cost_ci_high",
            ]
        )

    base_df = runs[runs["meta"] == baseline].set_index("seed")
    rows: list[dict[str, float | str | int]] = []

    for meta in sorted(set(runs["meta"])):
        if meta == baseline:
            continue
        meta_df = runs[runs["meta"] == meta].set_index("seed")
        common = sorted(set(base_df.index) & set(meta_df.index))
        if len(common) == 0:
            continue

        a_perf = meta_df.loc[common, perf_col].to_numpy(dtype=float)
        b_perf = base_df.loc[common, perf_col].to_numpy(dtype=float)
        a_cost = meta_df.loc[common, cost_col].to_numpy(dtype=float)
        b_cost = base_df.loc[common, cost_col].to_numpy(dtype=float)

        if len(common) == 1:
            # Single pair: no resampling variance, report the diff
            # itself as both endpoints to keep the schema rectangular.
            perf_diff = float(a_perf[0] - b_perf[0])
            cost_diff = float(a_cost[0] - b_cost[0])
            rows.append(
                {
                    "meta": meta,
                    "n_seeds": 1,
                    "perf_diff_mean": perf_diff,
                    "perf_ci_low": perf_diff,
                    "perf_ci_high": perf_diff,
                    "cost_diff_mean": cost_diff,
                    "cost_ci_low": cost_diff,
                    "cost_ci_high": cost_diff,
                }
            )
            continue

        perf_res = paired_bootstrap_ci(a_perf, b_perf)
        cost_res = paired_bootstrap_ci(a_cost, b_cost)
        rows.append(
            {
                "meta": meta,
                "n_seeds": int(len(common)),
                "perf_diff_mean": perf_res.diff_mean,
                "perf_ci_low": perf_res.ci_low,
                "perf_ci_high": perf_res.ci_high,
                "cost_diff_mean": cost_res.diff_mean,
                "cost_ci_low": cost_res.ci_low,
                "cost_ci_high": cost_res.ci_high,
            }
        )

    return pd.DataFrame(
        rows,
        columns=[
            "meta",
            "n_seeds",
            "perf_diff_mean",
            "perf_ci_low",
            "perf_ci_high",
            "cost_diff_mean",
            "cost_ci_low",
            "cost_ci_high",
        ],
    )


__all__ = [
    "ComparisonResult",
    "compare_meta_policies",
    "paired_bootstrap_ci",
    "pareto_dominance",
    "wilcoxon_signed_rank",
]
