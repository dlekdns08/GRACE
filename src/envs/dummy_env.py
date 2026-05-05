"""In-memory dummy environment for unit tests.

The DummyOvercookedEnv has no external dependencies (besides numpy) and
implements a minimal cooking loop on a 5x5 grid:

* Two agents move around. Action layout: ``0=noop, 1=up, 2=down, 3=left,
  4=right, 5=interact``.
* A single pot at a fixed location accepts up to 3 onions when an agent is
  adjacent and triggers the interact action while holding an onion.
* Once the pot has 3 onions it cooks for 5 ticks then becomes ready.
* When the pot is ready the episode terminates and both agents receive +1.
* The episode truncates at ``max_steps=50``.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .base import EnvObservation, EnvStep, OvercookedEnv
from .state_text import GenericPlayer, GenericPot, GenericState, state_to_text

_AGENT_IDS: tuple[str, str] = ("agent_0", "agent_1")
_GRID_SIZE = 5
_OBS_DIM = 8
_ACTION_SPACE_SIZE = 6
_MAX_STEPS = 50
_POT_POSITION: tuple[int, int] = (2, 0)
_ONIONS_NEEDED = 3
_COOK_TIME = 5


def _adjacent(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) == 1


class DummyOvercookedEnv(OvercookedEnv):
    """Tiny deterministic cooking environment for unit tests."""

    def __init__(self, max_steps: int = _MAX_STEPS) -> None:
        self._max_steps = int(max_steps)
        self._rng = np.random.default_rng(0)
        # Filled in by :meth:`reset`.
        self._positions: dict[str, tuple[int, int]] = {}
        self._held: dict[str, str | None] = {}
        self._pot_onions: int = 0
        self._pot_cook_remaining: int = 0
        self._pot_ready: bool = False
        self._timestep: int = 0
        self._soups_served: int = 0
        self._score: int = 0
        self._done: bool = False

    # ------------------------------------------------------------------ helpers
    def _start_positions(self) -> dict[str, tuple[int, int]]:
        # Deterministic, fixed start positions; seed only governs the rng used
        # for any future stochastic dynamics.
        return {"agent_0": (0, 0), "agent_1": (4, 4)}

    def _agent_obs(self, agent_id: str) -> np.ndarray:
        x, y = self._positions[agent_id]
        held = self._held[agent_id]
        held_code = {None: 0.0, "onion": 1.0, "dish": 2.0, "soup": 3.0}[held]
        return np.array(
            [
                float(x),
                float(y),
                held_code,
                float(self._pot_onions),
                float(self._pot_cook_remaining),
                1.0 if self._pot_ready else 0.0,
                float(self._timestep),
                float(self._max_steps),
            ],
            dtype=np.float32,
        )

    def _build_state(self) -> GenericState:
        players = [
            GenericPlayer(name=aid, position=self._positions[aid], held_item=self._held[aid])
            for aid in _AGENT_IDS
        ]
        pots = [
            GenericPot(
                onion_count=self._pot_onions,
                cooking_time_left=self._pot_cook_remaining,
                is_ready=self._pot_ready,
            )
        ]
        return GenericState(
            timestep=self._timestep,
            max_steps=self._max_steps,
            score=self._score,
            soups_served=self._soups_served,
            players=players,
            pots=pots,
        )

    def _build_observation(self) -> EnvObservation:
        raw = {aid: self._agent_obs(aid) for aid in _AGENT_IDS}
        text = state_to_text(self._build_state())
        info: dict[str, Any] = {
            "timestep": self._timestep,
            "pot_onions": self._pot_onions,
            "pot_ready": self._pot_ready,
        }
        return EnvObservation(raw=raw, text=text, info=info)

    def _apply_move(self, agent_id: str, action: int) -> None:
        x, y = self._positions[agent_id]
        if action == 1:  # up
            y = min(y + 1, _GRID_SIZE - 1)
        elif action == 2:  # down
            y = max(y - 1, 0)
        elif action == 3:  # left
            x = max(x - 1, 0)
        elif action == 4:  # right
            x = min(x + 1, _GRID_SIZE - 1)
        # Block agents from sharing a tile (deterministic tie-break: lower id wins).
        for other_id, other_pos in self._positions.items():
            if other_id != agent_id and other_pos == (x, y):
                return
        self._positions[agent_id] = (x, y)

    def _apply_interact(self, agent_id: str) -> None:
        if not _adjacent(self._positions[agent_id], _POT_POSITION):
            # Pick up an onion from anywhere as a free action when not adjacent
            # to the pot. Keeps the env easy enough for random rollouts to make
            # progress occasionally.
            if self._held[agent_id] is None:
                self._held[agent_id] = "onion"
            return
        # Adjacent to pot.
        if self._pot_ready:
            return
        if self._held[agent_id] == "onion" and self._pot_onions < _ONIONS_NEEDED:
            self._held[agent_id] = None
            self._pot_onions += 1
            if self._pot_onions == _ONIONS_NEEDED:
                self._pot_cook_remaining = _COOK_TIME

    def _advance_pot(self) -> None:
        if self._pot_cook_remaining > 0:
            self._pot_cook_remaining -= 1
            if self._pot_cook_remaining == 0:
                self._pot_ready = True

    # --------------------------------------------------------------------- API
    def reset(self, seed: int | None = None) -> EnvObservation:
        self._rng = np.random.default_rng(0 if seed is None else int(seed))
        self._positions = self._start_positions()
        self._held = {aid: None for aid in _AGENT_IDS}
        self._pot_onions = 0
        self._pot_cook_remaining = 0
        self._pot_ready = False
        self._timestep = 0
        self._soups_served = 0
        self._score = 0
        self._done = False
        return self._build_observation()

    def step(self, actions: dict[str, int]) -> EnvStep:
        if self._done:
            raise RuntimeError("step() called after episode end; call reset() first.")

        # Resolve moves first (deterministic order), then interactions, then pot.
        for aid in _AGENT_IDS:
            action = int(actions[aid])
            if action < 0 or action >= _ACTION_SPACE_SIZE:
                raise ValueError(
                    f"Invalid action {action} for {aid}; expected 0..{_ACTION_SPACE_SIZE - 1}"
                )
            if 1 <= action <= 4:
                self._apply_move(aid, action)

        for aid in _AGENT_IDS:
            if int(actions[aid]) == 5:
                self._apply_interact(aid)

        self._advance_pot()
        self._timestep += 1

        rewards = {aid: 0.0 for aid in _AGENT_IDS}
        terminated = False
        if self._pot_ready:
            for aid in _AGENT_IDS:
                rewards[aid] = 1.0
            self._score += 1
            self._soups_served += 1
            terminated = True

        truncated = (not terminated) and self._timestep >= self._max_steps
        self._done = terminated or truncated

        info: dict[str, Any] = {
            "soup_count": self._soups_served,
            "pot_onions": self._pot_onions,
            "pot_ready": self._pot_ready,
        }
        return EnvStep(
            obs=self._build_observation(),
            rewards=rewards,
            terminated=terminated,
            truncated=truncated,
            info=info,
        )

    def render(self, mode: str = "rgb_array") -> np.ndarray | None:
        return None

    @property
    def agent_ids(self) -> list[str]:
        return list(_AGENT_IDS)

    @property
    def action_space_size(self) -> int:
        return _ACTION_SPACE_SIZE

    @property
    def obs_dim(self) -> int:
        return _OBS_DIM
