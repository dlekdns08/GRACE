"""Unit tests for :mod:`src.eval.statistics` (Phase 11).

These tests exercise the four public utilities — paired-bootstrap CI,
Wilcoxon signed-rank, Pareto-frontier filter, and the cross-meta
comparison helper — on small, fabricated inputs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.eval.statistics import (
    ComparisonResult,
    compare_meta_policies,
    paired_bootstrap_ci,
    pareto_dominance,
    wilcoxon_signed_rank,
)


def test_paired_bootstrap_basic():
    """CI should bracket the true paired mean difference."""
    rng = np.random.default_rng(0)
    n = 50
    a = rng.normal(loc=1.0, scale=0.5, size=n)
    b = rng.normal(loc=0.0, scale=0.5, size=n)

    res = paired_bootstrap_ci(a, b, n_resamples=2000, seed=42)
    assert isinstance(res, ComparisonResult)
    assert res.method == "paired_bootstrap"
    assert res.n_pairs == n
    assert res.p_value is None
    # True diff is roughly 1.0; the CI must straddle it.
    assert res.ci_low <= 1.0 <= res.ci_high
    # Diff mean should be close to the empirical (a-b).mean().
    assert res.diff_mean == pytest.approx(float((a - b).mean()), abs=1e-9)
    # CI should be ordered.
    assert res.ci_low < res.ci_high


def test_paired_bootstrap_ci_width_shrinks():
    """More resamples should give a (loosely) more stable CI estimate."""
    rng = np.random.default_rng(1)
    n = 30
    a = rng.normal(loc=0.5, size=n)
    b = rng.normal(loc=0.0, size=n)

    # Average the absolute CI width over multiple seed draws to smooth
    # out Monte-Carlo noise; small-resample widths should not be tighter
    # on average than large-resample widths.
    def mean_width(n_resamples: int, n_trials: int = 5) -> float:
        widths = []
        for s in range(n_trials):
            res = paired_bootstrap_ci(a, b, n_resamples=n_resamples, seed=100 + s)
            widths.append(res.ci_high - res.ci_low)
        return float(np.mean(widths))

    width_small = mean_width(n_resamples=200)
    width_large = mean_width(n_resamples=5000)
    # The empirical SE of the percentile bound ≈ O(1/sqrt(n_resamples)),
    # so width_small should be at least as large as width_large modulo
    # noise. We use a generous slack.
    assert width_small >= width_large * 0.85


def test_wilcoxon_basic():
    """Clear positive-shift inputs should yield a small two-sided p-value."""
    rng = np.random.default_rng(2)
    n = 40
    base = rng.normal(scale=0.5, size=n)
    a = base + 1.0
    b = base
    res = wilcoxon_signed_rank(a, b)
    assert res.method == "wilcoxon"
    assert res.n_pairs == n
    assert res.p_value is not None
    assert res.p_value < 0.05
    assert res.diff_mean == pytest.approx(1.0, abs=1e-9)


def test_pareto_dominance():
    """Frontier of a 4-point set in (cost, perf) space."""
    df = pd.DataFrame(
        {
            "run": ["r1", "r2", "r3", "r4"],
            # cost (x): lower is better
            "mean_llm_calls": [10.0, 5.0, 20.0, 15.0],
            # perf (y): higher is better
            "mean_soup_count": [3.0, 1.0, 5.0, 4.0],
        }
    )
    out = pareto_dominance(df, cost_col="mean_llm_calls", perf_col="mean_soup_count")
    keep = set(out["run"])
    # r1: cost=10, perf=3 — beaten by r4 (cost=15 > 10 fails) -> not dominated by r4
    # but check vs r3: r3 has cost=20 > r1 -> doesn't dominate. r2 has cost=5 < 10
    # but perf=1 < 3 -> doesn't dominate r1. So r1 stays.
    # r2: cost=5, perf=1 — no one has lower cost AND higher perf -> stays.
    # r3: cost=20, perf=5 — no one has higher perf so r3 stays.
    # r4: cost=15, perf=4 — r3 has cost=20>15 (no) so r4 not dominated by r3.
    #                     r1 has cost=10<15 but perf=3<4 -> not dominated.
    #                     -> r4 stays.
    # Hence the frontier is all four points.
    assert keep == {"r1", "r2", "r3", "r4"}

    # Now add a strictly-dominated point: cost=12, perf=2 (worse than r1).
    df2 = pd.concat(
        [
            df,
            pd.DataFrame(
                {"run": ["r5"], "mean_llm_calls": [12.0], "mean_soup_count": [2.0]}
            ),
        ],
        ignore_index=True,
    )
    out2 = pareto_dominance(df2, cost_col="mean_llm_calls", perf_col="mean_soup_count")
    assert "r5" not in set(out2["run"])  # dominated by r1 (cost 10 < 12, perf 3 > 2)
    assert set(out2["run"]) == {"r1", "r2", "r3", "r4"}


def test_compare_meta_policies():
    """Cross-meta comparison: 2 metas (incl. baseline) x 3 seeds -> 1 row."""
    rng = np.random.default_rng(3)
    seeds = [0, 1, 2]
    rows = []
    # Baseline: fixed_k100 (worse soup, more calls)
    for s in seeds:
        rows.append(
            {
                "meta": "fixed_k100",
                "seed": s,
                "mean_soup_count": float(2.0 + 0.1 * rng.normal()),
                "mean_llm_calls": float(20.0 + 0.5 * rng.normal()),
            }
        )
    # Treatment: learned (better soup, fewer calls)
    for s in seeds:
        rows.append(
            {
                "meta": "learned",
                "seed": s,
                "mean_soup_count": float(3.0 + 0.1 * rng.normal()),
                "mean_llm_calls": float(10.0 + 0.5 * rng.normal()),
            }
        )
    df = pd.DataFrame(rows)
    out = compare_meta_policies(
        df,
        baseline="fixed_k100",
        perf_col="mean_soup_count",
        cost_col="mean_llm_calls",
    )

    assert list(out.columns) == [
        "meta",
        "n_seeds",
        "perf_diff_mean",
        "perf_ci_low",
        "perf_ci_high",
        "cost_diff_mean",
        "cost_ci_low",
        "cost_ci_high",
    ]
    assert len(out) == 1
    row = out.iloc[0]
    assert row["meta"] == "learned"
    assert int(row["n_seeds"]) == 3
    # learned beats fixed_k100 in performance and uses fewer calls.
    assert row["perf_diff_mean"] > 0
    assert row["cost_diff_mean"] < 0
    assert row["perf_ci_low"] <= row["perf_diff_mean"] <= row["perf_ci_high"]
    assert row["cost_ci_low"] <= row["cost_diff_mean"] <= row["cost_ci_high"]
