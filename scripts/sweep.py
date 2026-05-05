"""Print (and optionally execute) the cartesian product of a sweep spec.

Each ``KEY=v1,v2,...`` argument expands into one factor of the cross
product. This is intentionally simpler than Hydra's native ``-m`` flag
because it lets us preview the exact command list before running and
optionally drive each combination via ``subprocess.run``.

Examples::

    # Preview the commands
    python scripts/sweep.py meta=fixed_k10,fixed_k100 seed=0,1,2 env=dummy

    # Actually run them in-process, sequentially
    python scripts/sweep.py --run meta=fixed_k10,fixed_k100 seed=0,1,2 env=dummy
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterable
from itertools import product
from pathlib import Path

_TRAIN_SCRIPT = Path(__file__).resolve().parent / "train.py"


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
        overrides = [f"{k}={v}" for k, v in zip(keys, combo)]
        cmds.append([sys.executable, str(_TRAIN_SCRIPT), *overrides])
    return cmds


def main(argv: list[str]) -> int:
    run = "--run" in argv
    sweep_args = [a for a in argv if a != "--run"]
    cmds = build_commands(sweep_args)
    if not cmds:
        print(
            "No sweep arguments parsed. Pass KEY=v1,v2,... pairs.\n"
            "Example: python scripts/sweep.py meta=fixed_k10,fixed_k100 seed=0,1,2"
        )
        return 1

    if not run:
        print(f"# Sweep commands ({len(cmds)} total):")
        for cmd in cmds:
            print(" ".join(cmd))
        return 0

    print(f"# Executing {len(cmds)} sweep runs sequentially...")
    failures = 0
    for i, cmd in enumerate(cmds, start=1):
        print(f"\n[{i}/{len(cmds)}] {' '.join(cmd)}")
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            failures += 1
            print(f"  -> exited with code {result.returncode}")
    if failures:
        print(f"\n{failures}/{len(cmds)} runs failed.")
        return 2
    print(f"\nAll {len(cmds)} runs completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
