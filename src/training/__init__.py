"""Training loop primitives — rollout collection and PPO / GRPO updates."""

from src.training.grpo_trainer import (
    GRPOTrainer,
    MetaDecision,
    MetaRollout,
    collect_meta_rollout,
)
from src.training.ppo_trainer import PPOTrainer
from src.training.rollout import (
    SUBGOAL_TO_IDX,
    RolloutBatch,
    Transition,
    collect_rollout,
    subgoal_to_onehot,
)

__all__ = [
    "GRPOTrainer",
    "MetaDecision",
    "MetaRollout",
    "PPOTrainer",
    "RolloutBatch",
    "SUBGOAL_TO_IDX",
    "Transition",
    "collect_meta_rollout",
    "collect_rollout",
    "subgoal_to_onehot",
]
