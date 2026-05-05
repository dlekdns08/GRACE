"""Layout transfer evaluation (DESIGN H2).

Given a checkpoint trained on ``train_layout``, evaluate it zero-shot on
each of ``test_layouts`` and return one summary row per layout. The
implementation deliberately tolerates a missing ``overcooked_ai_py``
install — in that case the evaluation logs an error and skips the
layout, returning an empty DataFrame rather than crashing the caller.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from src.envs import OvercookedEnv
from src.eval.runner import run_eval
from src.llm.client import LLMClient
from src.policies.base import MetaPolicy, Policy

_log = logging.getLogger(__name__)


_TRANSFER_COLUMNS: list[str] = [
    "train_layout",
    "test_layout",
    "mean_return",
    "mean_soup_count",
    "mean_llm_calls",
    "n_episodes",
]


def _try_load_checkpoint(policy: Policy, checkpoint_path: str | Path) -> bool:
    """Load a torch state_dict into ``policy`` if the file exists."""
    path = Path(checkpoint_path)
    if not path.exists():
        _log.warning("Checkpoint %s not found; evaluating with fresh weights.", path)
        return False
    try:
        import torch

        state = torch.load(path, map_location="cpu", weights_only=True)
    except Exception:  # pragma: no cover - older torch without weights_only
        try:
            import torch

            state = torch.load(path, map_location="cpu")
        except Exception as exc:
            _log.error("Failed to load checkpoint %s: %s", path, exc)
            return False
    # Accept either a bare state_dict or our metadata-wrapped dict
    # (matching the format saved by ``scripts/train.py``).
    if isinstance(state, dict) and "policy_state_dict" in state:
        state_dict = state["policy_state_dict"]
    else:
        state_dict = state
    if hasattr(policy, "load_state_dict"):
        try:
            policy.load_state_dict(state_dict, strict=False)
            return True
        except Exception as exc:
            _log.error("load_state_dict failed for %s: %s", path, exc)
            return False
    return False


def _default_env_factory(layout: str) -> OvercookedEnv:
    """Default env factory: build a Carroll-Overcooked env for ``layout``."""
    from src.envs.python_env import PythonOvercookedEnv

    return PythonOvercookedEnv(layout=layout)


def evaluate_transfer(
    train_layout: str,
    test_layouts: list[str],
    policy_ctor: Callable[[], Policy],
    checkpoint_path: str | Path,
    meta_policy: MetaPolicy,
    llm_client: LLMClient,
    n_episodes: int = 10,
    env_factory: Callable[[str], OvercookedEnv] | None = None,
) -> pd.DataFrame:
    """Evaluate a checkpoint zero-shot on each of ``test_layouts``.

    Each row of the returned DataFrame has the columns
    ``train_layout, test_layout, mean_return, mean_soup_count,
    mean_llm_calls`` plus ``n_episodes`` for traceability. Layouts whose
    environment cannot be constructed (e.g. ``overcooked_ai_py`` missing)
    are silently skipped after an error log.

    ``env_factory`` lets callers (and tests) plug in custom env
    construction. The default uses :class:`PythonOvercookedEnv`.
    """
    rows: list[dict[str, Any]] = []
    factory = env_factory if env_factory is not None else _default_env_factory

    for layout in test_layouts:
        try:
            env = factory(layout)
        except Exception as exc:
            _log.error("Failed to build env for layout %r: %s", layout, exc)
            continue

        policy = policy_ctor()
        _try_load_checkpoint(policy, checkpoint_path)

        try:
            df = run_eval(
                env=env,
                policy=policy,
                meta_policy=meta_policy,
                llm_client=llm_client,
                n_episodes=n_episodes,
            )
        finally:
            close = getattr(env, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # pragma: no cover - best-effort cleanup
                    pass

        rows.append(
            {
                "train_layout": train_layout,
                "test_layout": layout,
                "mean_return": float(df["return_"].mean()) if not df.empty else 0.0,
                "mean_soup_count": float(df["soup_count"].mean()) if not df.empty else 0.0,
                "mean_llm_calls": float(df["llm_calls"].mean()) if not df.empty else 0.0,
                "n_episodes": int(len(df)),
            }
        )

    return pd.DataFrame(rows, columns=_TRANSFER_COLUMNS)
