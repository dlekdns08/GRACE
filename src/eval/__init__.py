"""Evaluation utilities — runner, metrics, transfer (DESIGN section 7).

Re-exports the public surface so call sites only need
``from src.eval import run_eval, aggregate_episodes`` etc.
"""

from src.eval.metrics import (
    EpisodeSummary,
    aggregate_episodes,
    call_step_distribution,
    cached_hit_rate,
    llm_calls_per_episode,
)
from src.eval.runner import run_eval
from src.eval.transfer import evaluate_transfer

__all__ = [
    "EpisodeSummary",
    "aggregate_episodes",
    "call_step_distribution",
    "cached_hit_rate",
    "evaluate_transfer",
    "llm_calls_per_episode",
    "run_eval",
]
