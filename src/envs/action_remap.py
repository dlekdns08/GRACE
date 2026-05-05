"""GRACE ↔ Carroll action-id remap.

Single source of truth lives in
``unity_env/Assets/Resources/Config/action_remap.json``. The Unity side reads
the same JSON (and also keeps a runtime-fast copy in
``Grace.Unity.Core.ActionIndexMap``).

GRACE order:   [STAY, N, S, E, W, INTERACT]   (ids 0..5)
Carroll order: [N,    S, E, W, STAY, INTERACT] (ids 0..5)

Use these helpers anywhere actions cross the Python ↔ Unity boundary
(side-channel payloads, parity tests, BC dataset converters).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# Default location relative to the repo root. Override by passing ``path=`` to
# :func:`load_remap`.
_DEFAULT_PATH = (
    Path(__file__).resolve().parents[2]
    / "unity_env"
    / "Assets"
    / "Resources"
    / "Config"
    / "action_remap.json"
)

# Hard-coded fallback that must stay in sync with the JSON. Used if the JSON
# file is missing (e.g. in a slim Python-only checkout for CI).
_FALLBACK = {
    "version": 1,
    "names": ["STAY", "N", "S", "E", "W", "INTERACT"],
    "grace_to_carroll": [4, 0, 1, 2, 3, 5],
    "carroll_to_grace": [1, 2, 3, 4, 0, 5],
}


@lru_cache(maxsize=4)
def load_remap(path: str | Path | None = None) -> dict:
    """Return the remap dict, loading from ``path`` (or the default JSON)."""
    p = Path(path) if path is not None else _DEFAULT_PATH
    if not p.exists():
        return dict(_FALLBACK)
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    # Drop any leading-underscore comment fields.
    return {k: v for k, v in data.items() if not k.startswith("_")}


def grace_to_carroll(action_id: int, path: str | Path | None = None) -> int:
    """Convert a GRACE action id (0..5) to Carroll's Python id."""
    return load_remap(path)["grace_to_carroll"][action_id]


def carroll_to_grace(action_id: int, path: str | Path | None = None) -> int:
    """Convert a Carroll Python action id (0..5) to GRACE's id."""
    return load_remap(path)["carroll_to_grace"][action_id]


__all__ = ["load_remap", "grace_to_carroll", "carroll_to_grace"]
