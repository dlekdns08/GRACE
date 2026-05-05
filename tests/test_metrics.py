"""Unit tests for the pure metric helpers in :mod:`src.eval.metrics`."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.eval.metrics import (
    EpisodeSummary,
    aggregate_episodes,
    call_step_distribution,
    cached_hit_rate,
    llm_calls_per_episode,
)


def _make_episodes(returns, soup, llm, cached):
    return pd.DataFrame(
        {
            "episode": list(range(len(returns))),
            "return": returns,
            "length": [10] * len(returns),
            "soup_count": soup,
            "llm_calls": llm,
            "cached_calls": cached,
        }
    )


def test_episode_summary_dataclass_round_trip():
    s = EpisodeSummary(
        episode=0, return_=1.5, length=20, soup_count=2, llm_calls=3, cached_calls=1
    )
    assert s.episode == 0
    assert s.return_ == pytest.approx(1.5)
    assert s.length == 20
    assert s.soup_count == 2
    assert s.llm_calls == 3
    assert s.cached_calls == 1


def test_aggregate_episodes_basic_with_return_column():
    df = _make_episodes([1.0, 3.0, 5.0], [0, 1, 2], [4, 6, 8], [0, 2, 4])
    out = aggregate_episodes(df)
    assert out["n_episodes"] == 3
    assert out["mean_return"] == pytest.approx(3.0)
    # ddof=0 std of [1, 3, 5]: sqrt(8/3)
    assert out["std_return"] == pytest.approx(np.sqrt(8 / 3))
    assert out["mean_soup_count"] == pytest.approx(1.0)
    assert out["mean_llm_calls"] == pytest.approx(6.0)
    assert out["mean_cached_calls"] == pytest.approx(2.0)


def test_aggregate_episodes_with_return_underscore_column():
    df = _make_episodes([2.0, 4.0], [1, 1], [2, 2], [0, 0])
    df = df.rename(columns={"return": "return_"})
    out = aggregate_episodes(df)
    assert out["mean_return"] == pytest.approx(3.0)
    assert out["n_episodes"] == 2


def test_aggregate_episodes_empty():
    out = aggregate_episodes(pd.DataFrame())
    assert out["n_episodes"] == 0
    assert out["mean_return"] == 0.0
    assert out["std_return"] == 0.0


def test_llm_calls_per_episode_counts_true_rows():
    transitions = pd.DataFrame(
        {
            "episode": [0, 0, 0, 1, 1, 2],
            "step": [0, 1, 2, 0, 1, 0],
            "llm_called": [True, False, True, False, False, True],
        }
    )
    out = llm_calls_per_episode(transitions)
    assert out.loc[0] == 2
    assert out.loc[1] == 0
    assert out.loc[2] == 1


def test_llm_calls_per_episode_empty_input():
    out = llm_calls_per_episode(pd.DataFrame())
    assert out.empty


def test_llm_calls_per_episode_no_episode_column_treats_as_one_episode():
    transitions = pd.DataFrame(
        {"step": [0, 1, 2], "llm_called": [True, False, True]}
    )
    out = llm_calls_per_episode(transitions)
    assert len(out) == 1
    assert int(out.iloc[0]) == 2


def test_cached_hit_rate_fraction():
    df = pd.DataFrame({"step": [0, 1, 2, 3], "cached": [True, False, True, True]})
    assert cached_hit_rate(df) == pytest.approx(0.75)


def test_cached_hit_rate_all_false():
    df = pd.DataFrame({"step": [0, 1], "cached": [False, False]})
    assert cached_hit_rate(df) == 0.0


def test_cached_hit_rate_empty():
    assert cached_hit_rate(pd.DataFrame()) == 0.0


def test_call_step_distribution_basic_histogram():
    df = pd.DataFrame({"step": [0, 49, 50, 99, 199]})
    hist = call_step_distribution(df, max_steps=200, n_bins=4)
    assert hist.shape == (4,)
    assert hist.sum() == 5
    # Bin edges 0, 50, 100, 150, 200 -> [0,49] in bin 0, [50,99] in bin 1, 199 in bin 3.
    assert hist[0] == 2
    assert hist[1] == 2
    assert hist[3] == 1


def test_call_step_distribution_clip_to_max_steps():
    df = pd.DataFrame({"step": [-5, 1000]})
    hist = call_step_distribution(df, max_steps=100, n_bins=2)
    # Both clipped: -5 -> 0 (bin 0), 1000 -> 100 (bin 1, the rightmost edge).
    assert hist.sum() == 2


def test_call_step_distribution_empty_returns_zeros():
    hist = call_step_distribution(pd.DataFrame(), max_steps=400, n_bins=10)
    assert hist.shape == (10,)
    assert hist.sum() == 0


def test_call_step_distribution_invalid_args():
    with pytest.raises(ValueError):
        call_step_distribution(pd.DataFrame({"step": [1]}), n_bins=0)
    with pytest.raises(ValueError):
        call_step_distribution(pd.DataFrame({"step": [1]}), max_steps=0)
