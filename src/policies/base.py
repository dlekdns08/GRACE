"""Abstract policy / meta-policy interfaces (DESIGN section 3.3).

`Policy` produces low-level actions; `MetaPolicy` produces a binary
"call the LLM now or not" decision. Keeping them as separate classes makes
ablation and baseline comparisons trivially clean — a heuristic
``FixedKMetaPolicy`` and a learned ``LearnedMetaPolicy`` satisfy the same
interface and can be swapped from a single config field.

`PolicyContext` bundles every signal a (meta-)policy might want to read in
a single place so we never have to plumb new arguments through the rollout
loop when a new meta-policy variant needs an extra feature.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from src.envs import EnvObservation

if TYPE_CHECKING:  # pragma: no cover - typing only
    import torch


@dataclass(slots=True)
class PolicyContext:
    """Everything a policy or meta-policy needs at decision time.

    `current_subgoal` maps each agent id to the most recent subgoal name
    the LLM emitted (or ``None`` if no subgoal has been assigned yet).
    `steps_since_llm_call` counts environment steps since the last LLM
    call (so a fresh subgoal has value 0). `episode_step` is the index of
    the current step within the running episode.
    """

    obs: EnvObservation
    current_subgoal: dict[str, str] | None
    steps_since_llm_call: int
    episode_step: int


class Policy(ABC):
    """Action policy: maps a `PolicyContext` to per-agent discrete actions."""

    @abstractmethod
    def act(self, ctx: PolicyContext) -> dict[str, int]:
        """Return a `{agent_id: action_index}` dict for the current step."""
        ...

    def get_logits(self, ctx: PolicyContext) -> "torch.Tensor | None":
        """Return per-agent action logits, or ``None`` if the policy is opaque.

        Default: not introspectable — heuristic / scripted policies do not
        expose differentiable logits and meta-policies that need them
        (e.g. entropy-based) must guard against ``None``.
        """
        return None


class MetaPolicy(ABC):
    """Binary call-the-LLM-or-not policy.

    `last_decision` mirrors the most recent boolean returned by
    :meth:`should_call_llm` so the rollout loop can log it without having
    to re-evaluate the policy.
    """

    last_decision: bool = False

    @abstractmethod
    def should_call_llm(self, ctx: PolicyContext) -> bool:
        """Decide whether to invoke the LLM at the current step."""
        ...

    def reset(self) -> None:
        """Clear any per-episode state. Default: reset only `last_decision`."""
        self.last_decision = False
