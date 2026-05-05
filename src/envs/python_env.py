"""Wrapper around Carroll's Overcooked-AI Python environment.

This module imports cleanly without ``overcooked_ai_py`` installed; the actual
import happens inside :meth:`PythonOvercookedEnv.__init__` so that test
collection on bare environments does not fail.

Notes on observation dim
------------------------
We use ``OvercookedEnv.featurize_state_mdp`` (which builds a
``MediumLevelActionManager`` lazily on first access). For the standard
layouts (``cramped_room``, ``asymmetric_advantages``) this returns a fixed
96-D float vector per agent — matching the value pinned in
``configs/env/*.yaml``. The much-larger ``lossless_state_encoding`` (a
spatial tensor) is intentionally not used here so the obs dim stays in
sync with the rest of the codebase.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from .base import EnvObservation, EnvStep, OvercookedEnv

_AGENT_IDS: tuple[str, str] = ("agent_0", "agent_1")


def _carroll_state_to_text(state: Any, mdp: Any, horizon: int) -> str:
    """Render an ``OvercookedState`` into the deterministic GRACE text format.

    Mirrors :func:`src.envs.state_text._generic_state_to_text` so the same
    prompt template / cache works for both backends.
    """
    # Soup orders served = total reward; we surface ``timestep`` and a
    # rough ``score`` proxy. The truthful score lives in info["episode"]
    # but isn't on the state itself, so we use timestep-relative info.
    score = 0  # state itself doesn't carry score; logged in step().info
    soups_served = 0

    lines: list[str] = [
        f"Step: {int(state.timestep)}/{int(horizon)}",
        f"Score: {score} (soups served: {soups_served})",
        "",
        "Agents:",
    ]

    # Carroll's players are an ordered tuple matching ``agent_0, agent_1``.
    for idx, player in enumerate(state.players):
        name = _AGENT_IDS[idx] if idx < len(_AGENT_IDS) else f"agent_{idx}"
        if player.held_object is None:
            held = "nothing"
        else:
            held = str(player.held_object.name)
        x, y = player.position
        lines.append(f"  - {name} at ({x},{y}), holding {held}")

    lines.append("")
    lines.append("Pots:")
    pot_locations = mdp.get_pot_locations()
    for idx, loc in enumerate(pot_locations):
        if state.has_object(loc):
            soup = state.get_object(loc)
            # Carroll's SoupState exposes _ingredients and is_cooking / is_ready.
            try:
                onion_count = sum(
                    1 for ing in soup.ingredients if ing == "onion"
                )
            except AttributeError:
                onion_count = len(getattr(soup, "_ingredients", []))
            is_ready = bool(getattr(soup, "is_ready", False))
            is_cooking = bool(getattr(soup, "is_cooking", False))
            cook_time_left = int(getattr(soup, "cook_time_remaining", 0))
            if is_ready:
                lines.append(f"  - Pot {idx}: ready to serve")
            elif is_cooking:
                lines.append(f"  - Pot {idx}: cooking, {cook_time_left}s remaining")
            elif onion_count == 0:
                lines.append(f"  - Pot {idx}: empty")
            else:
                lines.append(f"  - Pot {idx}: {onion_count}/3 onions, not started")
        else:
            lines.append(f"  - Pot {idx}: empty")

    return "\n".join(lines)


class PythonOvercookedEnv(OvercookedEnv):
    """Adapt Carroll's ``OvercookedEnv`` to the GRACE :class:`OvercookedEnv` API.

    Two agents are exposed under the names ``agent_0`` and ``agent_1``. Joint
    actions are supplied as ``{agent_id: int}`` and converted to the tuple
    format expected by overcooked-ai. The dense reward returned by the
    underlying env is split equally between the two agents (shared reward).
    """

    def __init__(
        self,
        layout_name: str | None = None,
        horizon: int = 400,
        featurize: str = "featurize",
        layout: str | None = None,
    ) -> None:
        try:
            from overcooked_ai_py.mdp.overcooked_env import OvercookedEnv as CarrollEnv
            from overcooked_ai_py.mdp.overcooked_mdp import OvercookedGridworld
        except ImportError as e:
            raise RuntimeError(
                "overcooked_ai_py is not installed. Install with "
                "`uv pip install -e '.[overcooked]'` (or "
                "`pip install 'overcooked-ai @ git+https://github.com/HumanCompatibleAI/overcooked_ai.git'`)."
            ) from e

        # Accept both ``layout_name=`` (existing call sites) and ``layout=``
        # (matches the Hydra config key) for ergonomics.
        resolved_layout = layout_name if layout_name is not None else layout
        if resolved_layout is None:
            resolved_layout = "cramped_room"

        self._layout_name = str(resolved_layout)
        self._horizon = int(horizon)
        self._featurize = str(featurize)

        self._mdp = OvercookedGridworld.from_layout_name(self._layout_name)
        self._env = CarrollEnv.from_mdp(self._mdp, horizon=self._horizon)

        from overcooked_ai_py.mdp.actions import Action

        self._actions_module = Action
        self._action_space_size = len(Action.ALL_ACTIONS)

        # Determine featurised observation shape by performing a dry encode.
        sample_obs = self._encode_raw_obs()
        self._obs_dim = int(sample_obs[_AGENT_IDS[0]].shape[0])

    # ------------------------------------------------------------------ helpers
    def _encode_raw_obs(self) -> dict[str, np.ndarray]:
        """Encode the current state as per-agent feature vectors.

        Uses ``OvercookedEnv.featurize_state_mdp`` (96-D for the standard
        layouts) by default. The lazy MLAM construction inside Carroll's
        env happens on the first call here.
        """
        state = self._env.state
        if self._featurize == "lossless":
            stacked = self._mdp.lossless_state_encoding(state)
        else:
            stacked = self._env.featurize_state_mdp(state)
        per_agent: dict[str, np.ndarray] = {}
        for idx, agent_id in enumerate(_AGENT_IDS):
            arr = np.asarray(stacked[idx], dtype=np.float32).reshape(-1)
            per_agent[agent_id] = arr
        return per_agent

    def _build_observation(self) -> EnvObservation:
        raw = self._encode_raw_obs()
        try:
            text = _carroll_state_to_text(self._env.state, self._mdp, self._horizon)
        except Exception:  # pragma: no cover - defensive fallback
            text = (
                f"Step: {self._env.state.timestep}/{self._horizon}\n"
                f"(text rendering unavailable)"
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
        truncated = bool(
            getattr(next_state, "timestep", 0) >= self._horizon and not terminated
        )
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
