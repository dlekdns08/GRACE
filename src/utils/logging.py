"""Rollout logging: in-memory buffers, parquet flush, optional W&B."""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd


@dataclass(slots=True)
class TransitionRecord:
    episode: int
    step: int
    reward: float
    subgoal: str | None
    llm_called: bool
    done: bool


@dataclass(slots=True)
class LLMCallRecord:
    episode: int
    step: int
    latency_ms: float
    tokens_in: int
    tokens_out: int
    cached: bool
    subgoal: str | None


@dataclass(slots=True)
class EpisodeRecord:
    episode: int
    return_: float
    length: int
    soup_count: int
    llm_calls: int
    cached_calls: int


class RolloutLogger:
    """Collects per-transition, per-LLM-call, and per-episode rows.

    Why parquet *and* W&B: W&B is good for live curves; parquet is the source of
    truth for offline analysis (DESIGN §6).
    """

    def __init__(self, run_dir: str | Path, use_wandb: bool = False, wandb_run: Any = None) -> None:
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.transitions: list[dict] = []
        self.llm_calls: list[dict] = []
        self.episodes: list[dict] = []
        self.use_wandb = use_wandb
        self._wandb_run = wandb_run
        self._t0 = time.perf_counter()

    def log_transition(self, rec: TransitionRecord) -> None:
        self.transitions.append(asdict(rec))

    def log_llm_call(self, rec: LLMCallRecord) -> None:
        self.llm_calls.append(asdict(rec))

    def log_episode(self, rec: EpisodeRecord) -> None:
        d = asdict(rec)
        d["return"] = d.pop("return_")
        self.episodes.append(d)
        if self.use_wandb and self._wandb_run is not None:
            self._wandb_run.log(
                {
                    "episode/return": d["return"],
                    "episode/length": d["length"],
                    "episode/soup_count": d["soup_count"],
                    "episode/llm_calls": d["llm_calls"],
                    "episode/cached_calls": d["cached_calls"],
                    "wallclock_sec": time.perf_counter() - self._t0,
                }
            )

    def log_scalar(self, key: str, value: float, step: int | None = None) -> None:
        if self.use_wandb and self._wandb_run is not None:
            payload = {key: value}
            self._wandb_run.log(payload, step=step)

    def flush(self) -> dict[str, Path]:
        paths = {}
        if self.transitions:
            p = self.run_dir / "transitions.parquet"
            pd.DataFrame(self.transitions).to_parquet(p, index=False)
            paths["transitions"] = p
        if self.llm_calls:
            p = self.run_dir / "llm_calls.parquet"
            pd.DataFrame(self.llm_calls).to_parquet(p, index=False)
            paths["llm_calls"] = p
        if self.episodes:
            p = self.run_dir / "episodes.parquet"
            pd.DataFrame(self.episodes).to_parquet(p, index=False)
            paths["episodes"] = p
        return paths
