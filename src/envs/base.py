"""Abstract environment interface for GRACE (DESIGN section 3.1).

All concrete environments (Unity, Carroll's Overcooked-AI, the in-memory
DummyOvercookedEnv used for tests) must satisfy this interface so that the
training and eval code remains agnostic to the underlying simulator.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np


@dataclass(slots=True)
class EnvObservation:
    """A single environment observation, exposed in two forms.

    ``raw`` feeds the RL policy (per-agent feature vectors); ``text`` feeds the
    LLM planner. Carrying both is intentional — recomputing one from the other
    every step is wasteful.
    """

    raw: dict[str, np.ndarray]
    text: str
    info: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class EnvStep:
    """The result of stepping the environment one tick."""

    obs: EnvObservation
    rewards: dict[str, float]
    terminated: bool
    truncated: bool
    info: dict[str, Any] = field(default_factory=dict)


class OvercookedEnv(ABC):
    """Abstract base class for all environment implementations."""

    @abstractmethod
    def reset(self, seed: int | None = None) -> EnvObservation:
        """Reset the environment and return the initial observation."""
        ...

    @abstractmethod
    def step(self, actions: dict[str, int]) -> EnvStep:
        """Apply one joint action and return the resulting :class:`EnvStep`."""
        ...

    @abstractmethod
    def render(self, mode: str = "rgb_array") -> np.ndarray | None:
        """Render the current state. May return ``None`` if rendering is unavailable."""
        ...

    @property
    @abstractmethod
    def agent_ids(self) -> list[str]:
        """Stable list of agent identifiers used as keys in action / observation dicts."""
        ...

    @property
    @abstractmethod
    def action_space_size(self) -> int:
        """Size of the discrete action space (per agent)."""
        ...

    @property
    @abstractmethod
    def obs_dim(self) -> int:
        """Per-agent dimensionality of the raw observation vector."""
        ...

    def close(self) -> None:
        """Release any resources. Default implementation is a no-op."""
        return None
