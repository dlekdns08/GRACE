"""Wrapper around Carroll's Overcooked-AI Python environment.

This module imports cleanly without ``overcooked_ai_py`` installed; the actual
import happens inside :meth:`PythonOvercookedEnv.__init__` so that test
collection on bare environments does not fail.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .base import EnvObservation, EnvStep, OvercookedEnv

_AGENT_IDS: tuple[str, str] = ("agent_0", "agent_1")


class PythonOvercookedEnv(OvercookedEnv):
    """Adapt Carroll's ``OvercookedEnv`` to the GRACE :class:`OvercookedEnv` API.

    Two agents are exposed under the names ``agent_0`` and ``agent_1``. Joint
    actions are supplied as ``{agent_id: int}`` and converted to the tuple
    format expected by overcooked-ai. The dense reward returned by the
    underlying env is split equally between the two agents (shared reward).
    """

    def __init__(
        self,
        layout_name: str = "cramped_room",
        horizon: int = 400,
        featurize: str = "lossless",
    ) -> None:
        try:
            from overcooked_ai_py.mdp.overcooked_mdp import OvercookedGridworld
            from overcooked_ai_py.mdp.overcooked_env import OvercookedEnv as CarrollEnv
        except ImportError as e:
            raise RuntimeError(
                "overcooked_ai_py is not installed. Install with "
                "`uv pip install -e '.[overcooked]'` (or "
                "`pip install 'overcooked-ai @ git+https://github.com/HumanCompatibleAI/overcooked_ai.git'`)."
            ) from e

        self._layout_name = layout_name
        self._horizon = horizon
        self._featurize = featurize

        self._mdp = OvercookedGridworld.from_layout_name(layout_name)
        self._env = CarrollEnv.from_mdp(self._mdp, horizon=horizon)

        # Determine featurised observation shape by performing a dry encode.
        sample_obs = self._encode_raw_obs()
        self._obs_dim = int(sample_obs[_AGENT_IDS[0]].shape[0])
        # Carroll's discrete action space size; Action.ALL_ACTIONS has 6 entries.
        from overcooked_ai_py.mdp.actions import Action

        self._action_space_size = len(Action.ALL_ACTIONS)
        self._actions_module = Action

    # ------------------------------------------------------------------ helpers
    def _encode_raw_obs(self) -> dict[str, np.ndarray]:
        state = self._env.state
        if self._featurize == "lossless":
            stacked = self._mdp.lossless_state_encoding(state)
        else:
            stacked = self._mdp.featurize_state(state, mlam=None)
        per_agent: dict[str, np.ndarray] = {}
        for idx, agent_id in enumerate(_AGENT_IDS):
            arr = np.asarray(stacked[idx], dtype=np.float32).reshape(-1)
            per_agent[agent_id] = arr
        return per_agent

    def _build_observation(self) -> EnvObservation:
        from .state_text import state_to_text  # local import to keep base lazy

        raw = self._encode_raw_obs()
        try:
            text = state_to_text(self._env.state)
        except NotImplementedError:
            # Until the overcooked-ai branch is wired in, fall back to a short
            # placeholder string. Phase 6 will replace this.
            text = (
                f"Step: {self._env.state.timestep}/{self._horizon}\n"
                f"(text representation pending overcooked_ai_py wiring)"
            )
        info: dict[str, Any] = {"timestep": int(self._env.state.timestep)}
        return EnvObservation(raw=raw, text=text, info=info)

    # --------------------------------------------------------------------- API
    def reset(self, seed: int | None = None) -> EnvObservation:
        if seed is not None:
            np.random.seed(seed)
        self._env.reset()
        return self._build_observation()

    def step(self, actions: dict[str, int]) -> EnvStep:
        joint_action = tuple(
            self._actions_module.INDEX_TO_ACTION[actions[a]] for a in _AGENT_IDS
        )
        next_state, reward, done, env_info = self._env.step(joint_action)
        per_agent_reward = float(reward) / 2.0
        rewards = {agent_id: per_agent_reward for agent_id in _AGENT_IDS}
        soup_count = int(env_info.get("episode", {}).get("ep_sparse_r", 0))
        info: dict[str, Any] = {"soup_count": soup_count, "raw_env_info": env_info}
        terminated = bool(done)
        truncated = bool(getattr(next_state, "timestep", 0) >= self._horizon and not terminated)
        return EnvStep(
            obs=self._build_observation(),
            rewards=rewards,
            terminated=terminated,
            truncated=truncated,
            info=info,
        )

    def render(self, mode: str = "rgb_array") -> np.ndarray | None:
        # Carroll's env has a string-based ``__repr__`` but no native rgb output;
        # return None so callers know rendering is unavailable.
        return None

    @property
    def agent_ids(self) -> list[str]:
        return list(_AGENT_IDS)

    @property
    def action_space_size(self) -> int:
        return self._action_space_size

    @property
    def obs_dim(self) -> int:
        return self._obs_dim
