"""Convert a Unity-recorded JSONL trajectory file to parquet.

Usage:

    python scripts/jsonl_to_parquet.py demos/session1.jsonl demos/session1.parquet

Thin CLI wrapper around :func:`src.envs.unity_parity.jsonl_to_parquet`.
The output schema matches what ``src.training.bc.load_demos_to_dataset``
expects (with ``raw_obs`` set to ``None`` and ``source="human_unity"``).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Allow running as `python scripts/jsonl_to_parquet.py` from repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.envs.unity_parity import jsonl_to_parquet  # noqa: E402

_log = logging.getLogger("jsonl_to_parquet")


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="jsonl_to_parquet",
        description="Convert a Unity-recorded JSONL trajectory to parquet.",
    )
    p.add_argument("jsonl", type=str, help="Path to input .jsonl file")
    p.add_argument("parquet", type=str, help="Path to output .parquet file")
    p.add_argument("--log-level", default="INFO")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    n_rows = jsonl_to_parquet(args.jsonl, args.parquet)
    print(f"wrote {n_rows} rows to {args.parquet}")
    return 0


if __name__ == "__main__":  # pragma: no cover - manual entry point
    raise SystemExit(main())
