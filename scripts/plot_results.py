"""Generate Pareto / learning-curve / call-step / transfer plots over a glob of runs.

Each run directory is expected to contain (as written by
:class:`src.utils.logging.RolloutLogger`):

* ``config.yaml`` — at minimum ``experiment.name`` (plus the resolved
  meta config that we use to color the plots).
* ``episodes.parquet`` — one row per training episode.
* ``transitions.parquet`` — one row per env step.
* ``llm_calls.parquet`` — one row per actual LLM call.
* ``transfer_results.parquet`` — optional; produced by ``scripts/eval_transfer.py``.

Usage::

    python scripts/plot_results.py "runs/*_seed*" --out figures/
    python scripts/plot_results.py "runs/*_seed*" --out figures/ --statistics
"""

from __future__ import annotations

import argparse
import glob
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

# Make ``src.*`` importable when this script is invoked from anywhere.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from omegaconf import OmegaConf  # noqa: E402

from src.eval.metrics import (  # noqa: E402
    aggregate_episodes,
    call_step_distribution,
    llm_calls_per_episode,
)
from src.eval.statistics import (  # noqa: E402
    compare_meta_policies,
    pareto_dominance,
)


@dataclass(slots=True)
class RunData:
    """One training run loaded from disk."""

    path: Path
    name: str  # experiment.name (used to color/group)
    meta_name: str  # short label for legend (meta-policy)
    train_layout: str  # env.layout / env.name (for transfer faceting)
    seed: int
    episodes: pd.DataFrame
    transitions: pd.DataFrame
    llm_calls: pd.DataFrame
    transfer: pd.DataFrame


def _read_optional_parquet(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception:
        return pd.DataFrame()


def _seed_from_cfg(cfg) -> int:
    try:
        return int(cfg.experiment.seed)
    except Exception:
        return -1


def _meta_label(cfg, fallback: str) -> str:
    try:
        return str(cfg.meta.name)
    except Exception:
        return fallback


def _train_layout(cfg, fallback: str) -> str:
    try:
        env = cfg.env
        if "layout" in env:
            return str(env.layout)
        if "name" in env:
            return str(env.name)
        return fallback
    except Exception:
        return fallback


def load_runs(pattern: str) -> list[RunData]:
    """Load every run directory matched by the glob ``pattern``."""
    runs: list[RunData] = []
    for path_str in sorted(glob.glob(pattern)):
        path = Path(path_str)
        if not path.is_dir():
            continue
        cfg_path = path / "config.yaml"
        if not cfg_path.exists():
            continue
        try:
            cfg = OmegaConf.load(cfg_path)
        except Exception:
            continue
        try:
            name = str(cfg.experiment.name)
        except Exception:
            name = path.name
        meta_name = _meta_label(cfg, fallback=name)
        train_layout = _train_layout(cfg, fallback=path.name)
        seed = _seed_from_cfg(cfg)

        episodes = _read_optional_parquet(path / "episodes.parquet")
        transitions = _read_optional_parquet(path / "transitions.parquet")
        llm_calls = _read_optional_parquet(path / "llm_calls.parquet")
        transfer = _read_optional_parquet(path / "transfer_results.parquet")

        runs.append(
            RunData(
                path=path,
                name=name,
                meta_name=meta_name,
                train_layout=train_layout,
                seed=seed,
                episodes=episodes,
                transitions=transitions,
                llm_calls=llm_calls,
                transfer=transfer,
            )
        )
    return runs


def _color_map(group_keys: list[str]) -> dict[str, tuple[float, float, float, float]]:
    cmap = plt.get_cmap("tab10")
    return {k: cmap(i % 10) for i, k in enumerate(sorted(set(group_keys)))}


# ----------------------------------------------------------------- summary frame
def _build_run_summary(runs: list[RunData]) -> pd.DataFrame:
    """Per-run aggregate row used by Pareto + statistics."""
    rows: list[dict] = []
    for run in runs:
        agg = aggregate_episodes(run.episodes)
        if agg["n_episodes"] == 0:
            continue
        rows.append(
            {
                "run": run.path.name,
                "meta": run.meta_name,
                "seed": run.seed,
                "mean_return": float(agg["mean_return"]),
                "mean_soup_count": float(agg["mean_soup_count"]),
                "mean_llm_calls": float(agg["mean_llm_calls"]),
            }
        )
    return pd.DataFrame(rows)


def plot_pareto(runs: list[RunData], out_path: Path) -> None:
    """One point per run with Pareto-frontier highlighting.

    Dominated points are drawn in light gray so the eye is drawn to the
    frontier; non-dominated points are coloured by meta-policy and the
    frontier itself is connected by a dashed black line in cost order.
    """
    fig, ax = plt.subplots(figsize=(6, 5))
    summary = _build_run_summary(runs)
    if summary.empty:
        ax.text(0.5, 0.5, "No runs with episode data", ha="center", va="center")
        ax.set_axis_off()
        fig.tight_layout()
        fig.savefig(out_path, dpi=120)
        plt.close(fig)
        return

    frontier = pareto_dominance(
        summary, cost_col="mean_llm_calls", perf_col="mean_soup_count"
    )
    frontier_keys = set(frontier["run"])

    colors = _color_map(summary["meta"].tolist())

    dominated = summary[~summary["run"].isin(frontier_keys)]
    if not dominated.empty:
        ax.scatter(
            dominated["mean_llm_calls"],
            dominated["mean_soup_count"],
            color="lightgray",
            s=40,
            alpha=0.75,
            label="dominated",
        )

    seen_legend: set[str] = set()
    for _, row in frontier.iterrows():
        meta = row["meta"]
        label = meta if meta not in seen_legend else None
        seen_legend.add(meta)
        ax.scatter(
            row["mean_llm_calls"],
            row["mean_soup_count"],
            color=colors[meta],
            s=80,
            edgecolor="black",
            linewidth=0.6,
            label=label,
            zorder=5,
        )

    if len(frontier) >= 2:
        f_sorted = frontier.sort_values("mean_llm_calls")
        ax.plot(
            f_sorted["mean_llm_calls"],
            f_sorted["mean_soup_count"],
            color="black",
            linestyle="--",
            linewidth=1.2,
            alpha=0.6,
            zorder=4,
        )

    ax.set_xlabel("Mean LLM calls per episode")
    ax.set_ylabel("Mean soup count")
    ax.set_title("Pareto: cost vs. performance")
    ax.grid(True, alpha=0.3)
    if seen_legend or not dominated.empty:
        ax.legend(title="meta-policy", loc="best")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def _episodes_returns(run: RunData) -> np.ndarray:
    if run.episodes.empty:
        return np.zeros((0,), dtype=float)
    if "return_" in run.episodes.columns:
        return run.episodes["return_"].to_numpy(dtype=float)
    if "return" in run.episodes.columns:
        return run.episodes["return"].to_numpy(dtype=float)
    return np.zeros((len(run.episodes),), dtype=float)


def plot_learning_curves(runs: list[RunData], out_path: Path) -> None:
    """Episode return vs. episode index, mean +/- std across seeds per group."""
    fig, ax = plt.subplots(figsize=(7, 5))
    by_group: dict[str, list[np.ndarray]] = defaultdict(list)
    for run in runs:
        ret = _episodes_returns(run)
        if ret.size > 0:
            by_group[run.meta_name].append(ret)

    colors = _color_map(list(by_group.keys()))

    for group, runs_returns in by_group.items():
        # Truncate to the shortest run so we have a rectangular array.
        min_len = min(len(r) for r in runs_returns)
        if min_len == 0:
            continue
        stacked = np.stack([r[:min_len] for r in runs_returns], axis=0)
        x = np.arange(min_len)
        mean = stacked.mean(axis=0)
        std = stacked.std(axis=0, ddof=0) if stacked.shape[0] > 1 else np.zeros_like(mean)
        ax.plot(x, mean, color=colors[group], label=f"{group} (n={stacked.shape[0]})")
        ax.fill_between(x, mean - std, mean + std, color=colors[group], alpha=0.2)

    ax.set_xlabel("Episode index")
    ax.set_ylabel("Episode return")
    ax.set_title("Learning curves")
    ax.grid(True, alpha=0.3)
    if by_group:
        ax.legend(title="meta-policy", loc="best")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_call_step_distribution(
    runs: list[RunData], out_path: Path, max_steps: int = 400, n_bins: int = 20
) -> None:
    """Histograms of LLM call timing within an episode, faceted by meta-policy."""
    by_group: dict[str, list[np.ndarray]] = defaultdict(list)
    for run in runs:
        if run.llm_calls.empty:
            continue
        hist = call_step_distribution(run.llm_calls, max_steps=max_steps, n_bins=n_bins)
        by_group[run.meta_name].append(hist)

    if not by_group:
        # Nothing to plot — emit a placeholder so callers still find a file.
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(0.5, 0.5, "No LLM calls logged", ha="center", va="center")
        ax.set_axis_off()
        fig.tight_layout()
        fig.savefig(out_path, dpi=120)
        plt.close(fig)
        return

    n_groups = len(by_group)
    fig, axes = plt.subplots(n_groups, 1, figsize=(7, max(2.5, 2.5 * n_groups)), sharex=True)
    if n_groups == 1:
        axes = [axes]

    edges = np.linspace(0.0, float(max_steps), n_bins + 1)
    centers = 0.5 * (edges[1:] + edges[:-1])
    width = (edges[1] - edges[0]) * 0.9
    colors = _color_map(list(by_group.keys()))

    for ax, (group, hists) in zip(axes, by_group.items(), strict=False):
        stacked = np.stack(hists, axis=0)
        mean = stacked.mean(axis=0)
        ax.bar(centers, mean, width=width, color=colors[group], alpha=0.85)
        ax.set_ylabel("calls")
        ax.set_title(f"meta={group} (n={stacked.shape[0]})")
        ax.grid(True, alpha=0.3, axis="y")

    axes[-1].set_xlabel("Step within episode")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def plot_transfer_results(runs: list[RunData], out_path: Path) -> bool:
    """Bar chart of mean soup count per (train_layout, test_layout).

    Returns ``True`` if any transfer rows were found and a real plot was
    rendered, ``False`` if the file is just a placeholder.
    """
    transfer_frames: list[pd.DataFrame] = []
    for run in runs:
        if run.transfer.empty:
            continue
        df = run.transfer.copy()
        df["seed"] = run.seed
        df["meta"] = run.meta_name
        transfer_frames.append(df)

    if not transfer_frames:
        fig, ax = plt.subplots(figsize=(6, 4))
        ax.text(0.5, 0.5, "No transfer_results.parquet found", ha="center", va="center")
        ax.set_axis_off()
        fig.tight_layout()
        fig.savefig(out_path, dpi=120)
        plt.close(fig)
        return False

    transfer = pd.concat(transfer_frames, ignore_index=True)
    grouped = (
        transfer.groupby(["train_layout", "test_layout"], dropna=False)["mean_soup_count"]
        .agg(["mean", "std", "count"])
        .reset_index()
        .fillna(0.0)
    )

    train_layouts = sorted(grouped["train_layout"].unique())
    test_layouts = sorted(grouped["test_layout"].unique())
    n_test = len(test_layouts)
    colors = _color_map(test_layouts)

    fig, ax = plt.subplots(figsize=(max(6.0, 1.5 * len(train_layouts) * n_test), 5))
    width = 0.8 / max(1, n_test)
    x_base = np.arange(len(train_layouts))

    for i, test_layout in enumerate(test_layouts):
        slice_ = grouped[grouped["test_layout"] == test_layout].set_index("train_layout")
        means = [
            float(slice_.loc[t, "mean"]) if t in slice_.index else 0.0 for t in train_layouts
        ]
        stds = [
            float(slice_.loc[t, "std"]) if t in slice_.index else 0.0 for t in train_layouts
        ]
        ax.bar(
            x_base + i * width,
            means,
            width=width,
            yerr=stds,
            color=colors[test_layout],
            alpha=0.85,
            label=test_layout,
            capsize=3,
        )

    ax.set_xticks(x_base + width * (n_test - 1) / 2)
    ax.set_xticklabels(train_layouts, rotation=20, ha="right")
    ax.set_xlabel("Train layout")
    ax.set_ylabel("Mean soup count (transfer)")
    ax.set_title("Zero-shot transfer to held-out layouts")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(title="test layout", loc="best")
    fig.tight_layout()
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return True


def print_summary_table(runs: list[RunData]) -> None:
    """Print a per-run summary table to stdout."""
    rows: list[dict] = []
    for run in runs:
        agg = aggregate_episodes(run.episodes)
        per_ep = llm_calls_per_episode(run.transitions)
        mean_calls_from_transitions = float(per_ep.mean()) if not per_ep.empty else 0.0
        rows.append(
            {
                "run": run.path.name,
                "meta": run.meta_name,
                "seed": run.seed,
                "n_ep": agg["n_episodes"],
                "mean_return": round(agg["mean_return"], 3),
                "std_return": round(agg["std_return"], 3),
                "mean_soup": round(agg["mean_soup_count"], 3),
                "mean_llm_calls": round(agg["mean_llm_calls"], 3),
                "mean_calls_tx": round(mean_calls_from_transitions, 3),
            }
        )
    if not rows:
        print("(no runs found)")
        return
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))


def emit_statistics(runs: list[RunData], out_dir: Path) -> None:
    """Compute and persist the cross-seed bootstrap CI table."""
    summary = _build_run_summary(runs)
    if summary.empty:
        print("(no runs to compute statistics on)")
        return
    metas = sorted(set(summary["meta"]))
    baseline = "fixed_k100" if "fixed_k100" in metas else metas[0]

    table = compare_meta_policies(
        summary,
        baseline=baseline,
        perf_col="mean_soup_count",
        cost_col="mean_llm_calls",
    )
    print(f"\n# Statistics vs baseline {baseline!r} (paired bootstrap, 95% CI):")
    if table.empty:
        print("(no comparable metas)")
    else:
        print(table.round(4).to_string(index=False))

    out_csv = out_dir / "statistics.csv"
    table.to_csv(out_csv, index=False)
    print(f"\nStatistics CSV written to {out_csv.resolve()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pattern", help="Glob matching run directories")
    parser.add_argument("--out", default="figures/", help="Output directory for .png figures")
    parser.add_argument(
        "--max-steps", type=int, default=400, help="Max episode length (for histogram x-axis)"
    )
    parser.add_argument("--n-bins", type=int, default=20, help="Histogram bin count")
    parser.add_argument(
        "--statistics",
        action="store_true",
        help="Print and save bootstrap CI table comparing metas to fixed_k100.",
    )
    args = parser.parse_args(argv)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    runs = load_runs(args.pattern)
    if not runs:
        print(f"No runs matched pattern {args.pattern!r}")
        return 1

    print(f"Loaded {len(runs)} run(s) from {args.pattern!r}")

    plot_pareto(runs, out_dir / "pareto.png")
    plot_learning_curves(runs, out_dir / "learning_curves.png")
    plot_call_step_distribution(
        runs,
        out_dir / "call_step_distribution.png",
        max_steps=args.max_steps,
        n_bins=args.n_bins,
    )
    has_transfer = plot_transfer_results(runs, out_dir / "transfer_results.png")
    if has_transfer:
        print(f"Transfer plot written to {out_dir / 'transfer_results.png'}")

    print_summary_table(runs)

    if args.statistics:
        emit_statistics(runs, out_dir)

    print(f"\nFigures written to {out_dir.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
