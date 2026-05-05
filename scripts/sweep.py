"""Sweep harness for ``scripts/train.py`` (DESIGN section 5).

Each ``KEY=v1,v2,...`` argument expands into one factor of the cross
product. We layer on top of Hydra's native ``-m`` flag because we want
fine-grained control over manifest writing, parallelism, and skip-on-
existence. The script is intentionally usable both as a preview tool
(no ``--run``) and as a real launcher.

Examples::

    # Preview the commands without running anything
    python scripts/sweep.py meta=fixed_k10,fixed_k100 seed=0,1,2 env=dummy

    # Launch them in parallel and write a manifest of run dirs
    python scripts/sweep.py --run --parallel 4 \\
        --manifest runs/sweep_manifest.json \\
        meta=fixed_k10,fixed_k100 seed=0,1,2 env=dummy
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from collections.abc import Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from itertools import product
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_TRAIN_SCRIPT = Path(__file__).resolve().parent / "train.py"

# Pulled from the Hydra sink line that train.py prints on every run.
# We also accept the run-dir written by save_resolved_config indirectly.
_RUN_DIR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"saved policy checkpoint:\s*(\S+)/policy\.pt"),
    re.compile(r"Wrote logs:\s*\{[^}]*'transitions':\s*'(\S+)/transitions\.parquet'"),
)


# ----------------------------------------------------------------------- parsing
def parse_kv(arg: str) -> tuple[str, list[str]]:
    """Split ``KEY=v1,v2`` into ``("KEY", ["v1", "v2"])``."""
    if "=" not in arg:
        raise ValueError(f"Sweep arg {arg!r} must be of the form KEY=v1,v2,...")
    k, v = arg.split("=", 1)
    return k, v.split(",")


def build_commands(argv: Iterable[str]) -> list[list[str]]:
    """Build the list of ``[python, train.py, override...]`` commands."""
    parsed = [parse_kv(a) for a in argv if "=" in a]
    if not parsed:
        return []
    keys = [k for k, _ in parsed]
    values_lists = [v for _, v in parsed]
    cmds: list[list[str]] = []
    for combo in product(*values_lists):
        overrides = [f"{k}={v}" for k, v in zip(keys, combo, strict=False)]
        cmds.append([sys.executable, str(_TRAIN_SCRIPT), *overrides])
    return cmds


# ------------------------------------------------------------- run-dir prediction
def _meta_value(overrides: list[str], key: str, default: str) -> str:
    for o in overrides:
        if "=" not in o:
            continue
        k, v = o.split("=", 1)
        if k == key:
            return v
    return default


def _predict_run_prefix(overrides: list[str]) -> str:
    """Approximate the ``experiment.name_seedN`` prefix that Hydra will use.

    Hydra appends a ``_<timestamp>`` suffix on top of this; we treat the
    prefix alone as the dedup key for ``--retry-failed``.
    """
    meta = _meta_value(overrides, "meta", "fixed_k100")
    env = _meta_value(overrides, "env", "cramped_room")
    policy = _meta_value(overrides, "policy", "ppo")
    seed = _meta_value(overrides, "experiment.seed", _meta_value(overrides, "seed", "0"))
    return f"{meta}_{env}_{policy}_seed{seed}"


def _existing_runs_for_prefix(prefix: str, runs_dir: Path) -> list[Path]:
    """Return all directories matching ``runs/<prefix>_*`` with a ``config.yaml``."""
    if not runs_dir.exists():
        return []
    out: list[Path] = []
    for child in sorted(runs_dir.iterdir()):
        if not child.is_dir():
            continue
        if not child.name.startswith(prefix + "_"):
            continue
        if (child / "config.yaml").exists():
            out.append(child)
    return out


# ----------------------------------------------------------------- subprocess exec
@dataclass(slots=True)
class SweepResult:
    """One subprocess invocation's outcome."""

    cmd: list[str]
    returncode: int
    elapsed: float
    run_dir: str | None
    skipped: bool = False
    stdout_tail: list[str] = field(default_factory=list)


def _extract_run_dir(stdout: str) -> str | None:
    for pattern in _RUN_DIR_PATTERNS:
        m = pattern.search(stdout)
        if m:
            return m.group(1)
    return None


def _run_one(cmd: list[str]) -> SweepResult:
    """Run a single training command, capturing stdout for run-dir extraction."""
    start = time.perf_counter()
    proc = subprocess.run(
        cmd,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    elapsed = time.perf_counter() - start
    out = proc.stdout or ""
    sys.stdout.write(out)
    sys.stdout.flush()
    run_dir = _extract_run_dir(out)
    tail_lines = out.splitlines()[-5:] if out else []
    return SweepResult(
        cmd=cmd,
        returncode=int(proc.returncode),
        elapsed=elapsed,
        run_dir=run_dir,
        stdout_tail=tail_lines,
    )


def _execute_sequential(cmds: list[list[str]]) -> list[SweepResult]:
    results: list[SweepResult] = []
    for i, cmd in enumerate(cmds, start=1):
        print(f"\n[{i}/{len(cmds)}] {' '.join(cmd)}")
        res = _run_one(cmd)
        print(f"  -> rc={res.returncode} elapsed={res.elapsed:.1f}s run_dir={res.run_dir}")
        results.append(res)
    return results


def _execute_parallel(cmds: list[list[str]], parallel: int) -> list[SweepResult]:
    print(f"# Launching {len(cmds)} runs with parallelism={parallel}...")
    results: list[SweepResult] = []
    with ProcessPoolExecutor(max_workers=parallel) as pool:
        futures = {pool.submit(_run_one, cmd): cmd for cmd in cmds}
        for i, fut in enumerate(as_completed(futures), start=1):
            res = fut.result()
            print(
                f"[{i}/{len(cmds)}] rc={res.returncode} "
                f"elapsed={res.elapsed:.1f}s run_dir={res.run_dir} "
                f"cmd={' '.join(res.cmd)}"
            )
            results.append(res)
    return results


# ----------------------------------------------------------------- manifest
def _write_manifest(path: Path, results: list[SweepResult]) -> None:
    payload = {
        "n_runs": len(results),
        "n_succeeded": sum(1 for r in results if r.returncode == 0 and not r.skipped),
        "n_skipped": sum(1 for r in results if r.skipped),
        "n_failed": sum(1 for r in results if r.returncode != 0 and not r.skipped),
        "runs": [
            {
                "cmd": r.cmd,
                "returncode": r.returncode,
                "elapsed_seconds": r.elapsed,
                "run_dir": r.run_dir,
                "skipped": r.skipped,
                "stdout_tail": r.stdout_tail,
            }
            for r in results
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2))
    print(f"Wrote manifest: {path}")


# ----------------------------------------------------------------- CLI
def _parse_args(argv: list[str]) -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--run", action="store_true", help="Actually execute the commands (default: preview)."
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=1,
        help="Number of concurrent training subprocesses (default: 1).",
    )
    parser.add_argument(
        "--manifest",
        default=None,
        help="Path to write a JSON manifest of all runs (created on --run).",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="Skip combinations whose run dir already exists (allows resuming a sweep).",
    )
    parser.add_argument(
        "--runs-dir",
        default="runs",
        help="Where to look for existing run dirs when --retry-failed is set.",
    )
    return parser.parse_known_args(argv)


def main(argv: list[str]) -> int:
    args, sweep_args = _parse_args(argv)
    cmds = build_commands(sweep_args)
    if not cmds:
        print(
            "No sweep arguments parsed. Pass KEY=v1,v2,... pairs.\n"
            "Example: python scripts/sweep.py meta=fixed_k10,fixed_k100 seed=0,1,2"
        )
        return 1

    if not args.run:
        print(f"# Sweep commands ({len(cmds)} total):")
        for cmd in cmds:
            print(" ".join(cmd))
        return 0

    runs_dir = Path(args.runs_dir)
    skipped_results: list[SweepResult] = []
    runnable_cmds: list[list[str]] = []

    for cmd in cmds:
        overrides = cmd[2:]
        if args.retry_failed:
            prefix = _predict_run_prefix(overrides)
            existing = _existing_runs_for_prefix(prefix, runs_dir)
            if existing:
                first = existing[0]
                print(f"# Skipping (already exists): {first} for prefix {prefix!r}")
                skipped_results.append(
                    SweepResult(
                        cmd=cmd,
                        returncode=0,
                        elapsed=0.0,
                        run_dir=str(first),
                        skipped=True,
                    )
                )
                continue
        runnable_cmds.append(cmd)

    print(
        f"# Executing {len(runnable_cmds)} of {len(cmds)} sweep runs "
        f"(skipped {len(skipped_results)}); parallel={args.parallel}..."
    )
    overall_start = time.perf_counter()

    if args.parallel <= 1:
        executed = _execute_sequential(runnable_cmds)
    else:
        executed = _execute_parallel(runnable_cmds, args.parallel)

    total_elapsed = time.perf_counter() - overall_start
    results = skipped_results + executed

    failures = sum(1 for r in results if r.returncode != 0 and not r.skipped)
    succeeded = sum(1 for r in results if r.returncode == 0 and not r.skipped)
    print(
        f"\nSweep complete: {succeeded} ok, {failures} failed, "
        f"{len(skipped_results)} skipped — total wall time {total_elapsed:.1f}s."
    )

    if args.manifest:
        _write_manifest(Path(args.manifest), results)

    return 2 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
