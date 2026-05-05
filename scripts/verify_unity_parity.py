"""Verify state-by-state parity between Unity and Carroll Python (Phase G6).

Usage:

    python scripts/verify_unity_parity.py \\
        --jsonl demos/session1.jsonl \\
        --layout cramped_room \\
        --report runs/parity_report.md

Steps performed:

1. Load JSONL, group into per-episode trajectories.
2. For each episode, replay through Carroll's overcooked-ai with the
   same action sequence.
3. Diff Unity vs Carroll state texts step by step.
4. Write a markdown report with per-episode and aggregate parity rates,
   first-divergence steps, and the first <=3 mismatched step diffs per
   episode.

Exit codes:
    0 -- all episodes had parity_rate == 1.0
    1 -- at least one episode diverged
    2 -- overcooked_ai_py is not installed (cannot verify)
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

# Allow running as `python scripts/verify_unity_parity.py` from repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.envs.unity_parity import (  # noqa: E402
    EpisodeTrajectory,
    ParityDiff,
    diff_episode,
    group_into_episodes,
    load_jsonl,
    parity_summary,
    replay_through_carroll,
)

_log = logging.getLogger("verify_unity_parity")

_MAX_DIFFS_PER_EPISODE = 3  # how many mismatched steps to embed in the report


def _check_overcooked_available() -> bool:
    try:
        import overcooked_ai_py  # noqa: F401
    except ImportError:
        return False
    return True


def _format_diff_block(diff: ParityDiff) -> str:
    """Render one ParityDiff as a markdown fenced block."""
    lines = [
        f"#### Step {diff.step}",
        "",
        "Unity:",
        "```",
        diff.unity_text,
        "```",
        "",
        "Carroll:",
        "```",
        diff.carroll_text,
        "```",
        "",
        "Unified diff:",
        "```diff",
        *diff.diff_lines,
        "```",
        "",
    ]
    return "\n".join(lines)


def _format_episode_section(
    traj: EpisodeTrajectory,
    diffs: list[ParityDiff],
    summary: dict[str, Any],
) -> str:
    """Render a single episode's section of the parity report."""
    lines = [
        f"## Episode {traj.episode}",
        "",
        f"- Steps: **{summary['n_steps_total']}**",
        f"- Differing steps: **{summary['n_steps_diff']}**",
        f"- Parity rate: **{summary['parity_rate']:.4f}**",
        f"- First divergence: "
        f"**{'(perfect match)' if summary['first_diff_step'] is None else summary['first_diff_step']}**",
        f"- Recorded done at step: **{traj.done_at if traj.done_at is not None else '(none)'}**",
        "",
    ]
    if diffs:
        lines.append(f"### First {min(_MAX_DIFFS_PER_EPISODE, len(diffs))} mismatched step(s)")
        lines.append("")
        for diff in diffs[:_MAX_DIFFS_PER_EPISODE]:
            lines.append(_format_diff_block(diff))
    return "\n".join(lines)


def _write_report(
    report_path: Path,
    layout: str,
    jsonl_path: Path,
    per_episode: list[tuple[EpisodeTrajectory, list[ParityDiff], dict[str, Any]]],
    aggregate: dict[str, Any],
) -> None:
    sections: list[str] = [
        "# Unity <-> Carroll Parity Report",
        "",
        f"- JSONL: `{jsonl_path}`",
        f"- Layout: `{layout}`",
        f"- Episodes: **{len(per_episode)}**",
        f"- Aggregate steps: **{aggregate['n_steps_total']}**",
        f"- Aggregate differing steps: **{aggregate['n_steps_diff']}**",
        f"- Aggregate parity rate: **{aggregate['parity_rate']:.4f}**",
        f"- Verdict: **{'PASS' if aggregate['parity_rate'] >= 1.0 else 'FAIL'}**",
        "",
        "Per-episode parity rates:",
        "",
        "| Episode | Steps | Differing | Parity rate | First diff |",
        "|---|---|---|---|---|",
    ]
    for traj, _diffs, summary in per_episode:
        first = (
            "-" if summary["first_diff_step"] is None else str(summary["first_diff_step"])
        )
        sections.append(
            f"| {traj.episode} | {summary['n_steps_total']} | "
            f"{summary['n_steps_diff']} | {summary['parity_rate']:.4f} | {first} |"
        )
    sections.append("")

    for traj, diffs, summary in per_episode:
        sections.append(_format_episode_section(traj, diffs, summary))

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(sections), encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    if not _check_overcooked_available():
        _log.error(
            "overcooked_ai_py is not installed; cannot replay trajectories. "
            "Install with `uv pip install -e '.[overcooked]'`."
        )
        return 2

    jsonl_path = Path(args.jsonl)
    report_path = Path(args.report)

    records = load_jsonl(jsonl_path)
    episodes = group_into_episodes(records, n_agents=int(args.n_agents))
    if not episodes:
        _log.error("no episodes found in %s", jsonl_path)
        return 1

    per_episode: list[tuple[EpisodeTrajectory, list[ParityDiff], dict[str, Any]]] = []
    agg_total = 0
    agg_diff = 0

    for traj in episodes:
        traj.layout = args.layout
        carroll_texts = replay_through_carroll(
            traj, layout=args.layout, horizon=int(args.horizon)
        )
        diffs = diff_episode(traj, carroll_texts)
        summary = parity_summary(diffs, total_steps=len(traj.state_texts))
        per_episode.append((traj, diffs, summary))
        agg_total += int(summary["n_steps_total"])
        agg_diff += int(summary["n_steps_diff"])

        _log.info(
            "episode %d: parity_rate=%.4f (%d/%d differing)",
            traj.episode,
            summary["parity_rate"],
            summary["n_steps_diff"],
            summary["n_steps_total"],
        )

    if agg_total == 0:
        agg_rate = 1.0 if agg_diff == 0 else 0.0
    else:
        agg_rate = max(0.0, min(1.0, 1.0 - agg_diff / agg_total))
    aggregate = {
        "n_steps_total": agg_total,
        "n_steps_diff": agg_diff,
        "parity_rate": float(agg_rate),
    }

    _write_report(
        report_path=report_path,
        layout=args.layout,
        jsonl_path=jsonl_path,
        per_episode=per_episode,
        aggregate=aggregate,
    )
    _log.info("wrote parity report to %s", report_path)

    # Exit code: 0 only if every episode is perfectly faithful.
    all_perfect = all(s["parity_rate"] >= 1.0 for _, _, s in per_episode)
    return 0 if all_perfect else 1


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="verify_unity_parity",
        description=(
            "Verify state-by-state parity between Unity-recorded JSONL "
            "and Carroll's overcooked-ai Python simulation."
        ),
    )
    p.add_argument("--jsonl", required=True, type=str, help="Input .jsonl path")
    p.add_argument(
        "--layout",
        required=True,
        type=str,
        help="Carroll layout name (e.g. cramped_room, asymmetric_advantages)",
    )
    p.add_argument(
        "--report",
        required=True,
        type=str,
        help="Output markdown report path",
    )
    p.add_argument("--horizon", type=int, default=400, help="Episode horizon (Carroll)")
    p.add_argument("--n-agents", dest="n_agents", type=int, default=2)
    p.add_argument("--log-level", default="INFO")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    return run(args)


if __name__ == "__main__":  # pragma: no cover - manual entry point
    raise SystemExit(main())
