"""Config helpers — Hydra/OmegaConf interop and run-dir formatting."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from omegaconf import DictConfig, OmegaConf


def format_run_dir(cfg: DictConfig, base: str | Path = "runs") -> Path:
    """Build a unique, descriptive run directory from cfg fields."""
    name = cfg.experiment.name
    seed = cfg.experiment.seed
    ts = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    p = Path(base) / f"{name}_{ts}_seed{seed}"
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_resolved_config(cfg: DictConfig, path: str | Path) -> None:
    """Snapshot the *resolved* config to disk for reproducibility."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(OmegaConf.to_yaml(cfg, resolve=True))
