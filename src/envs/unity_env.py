"""Adapter from Unity ML-Agents to GRACE's :class:`OvercookedEnv`.

This module is intentionally importable on machines that do **not** have the
``mlagents-envs`` package installed: the heavy import happens lazily inside
:meth:`UnityOvercookedEnv.__init__`. That way tests, lint, and CI on
mlagents-free environments still work.

The Unity build is expected to register ``StateSerializer`` (a side channel
with GUID ``621f0a70-4f87-11ea-a6bf-784f4387d1f7``) which pushes the
human-readable text observation matching :func:`src.envs.state_text.state_to_text`.
See ``unity_env/Assets/Scripts/StateSerializer.cs``.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

import numpy as np

from .base import EnvObservation, EnvStep, OvercookedEnv

if TYPE_CHECKING:  # pragma: no cover - typing-only imports
    from mlagents_envs.environment import UnityEnvironment
    from mlagents_envs.side_channel.side_channel import (
        IncomingMessage,
        SideChannel,
    )


_SIDE_CHANNEL_GUID = "621f0a70-4f87-11ea-a6bf-784f4387d1f7"
_INSTALL_HINT = (
    "mlagents-envs is not installed. Install with `pip install grace[unity]` "
    "(or `pip install mlagents-envs`)."
)


def _make_text_obs_side_channel() -> "SideChannel":
    """Construct a :class:`SideChannel` subclass that captures text observations.

    Defined as a factory so the ``mlagents_envs`` import remains lazy: the
    parent class only exists at call time, after we've successfully imported.
    """

    from mlagents_envs.side_channel.side_channel import (
        IncomingMessage,
        SideChannel,
    )

    class _TextObsSideChannel(SideChannel):  # type: ignore[misc]
        """Side channel that stores the latest UTF-8 text observation."""

        def __init__(self) -> None:
            super().__init__(uuid.UUID(_SIDE_CHANNEL_GUID))
            self.last_text: str = ""

        def on_message_received(self, msg: "IncomingMessage") -> None:
            self.last_text = msg.read_string()

    return _TextObsSideChannel()


class UnityOvercookedEnv(OvercookedEnv):
    """Adapter from ML-Agents Unity environment to GRACE's :class:`OvercookedEnv`.

    The Unity build must register the ``StateSerializer`` side channel
    (GUID ``621f0a70-4f87-11ea-a6bf-784f4387d1f7``) which pushes the text
    observation. The discrete action space is fixed at 7 to match
    ``ChefAgent.cs`` (``0=noop``, ``1..4=move``, ``5=pickup/drop``,
    ``6=interact``).

    Agent name -> ML-Agents ``agent_id`` mapping
    --------------------------------------------
    ML-Agents groups agents by ``BehaviorName``; individual agents are then
    distinguished by an integer ``agent_id`` issued by Unity. We assume there
    is exactly **one** behavior in the build (the kitchen). The two agents
    are aligned by sorting both sides:
    ``sorted(agent_names)[i] <-> sorted(decision_steps.agent_id)[i]``.
    This is the simplest stable mapping and makes the adapter agnostic to
    the order in which Unity happens to register agents on a given run.
    """

    SIDE_CHANNEL_ID: str = _SIDE_CHANNEL_GUID

    def __init__(
        self,
        build_path: str | None = None,
        worker_id: int = 0,
        no_graphics: bool = True,
        seed: int = 0,
        time_scale: float = 20.0,
        agent_names: tuple[str, str] = ("agent_0", "agent_1"),
        timeout_wait: float = 60.0,
    ) -> None:
        try:
            from mlagents_envs.environment import UnityEnvironment
            from mlagents_envs.side_channel.engine_configuration_channel import (
                EngineConfigurationChannel,
            )
        except ImportError as e:
            raise RuntimeError(_INSTALL_HINT) from e

        if len(agent_names) != 2:
            raise ValueError(
                f"agent_names must have exactly two entries; got {agent_names!r}."
            )

        self._agent_names: tuple[str, str] = tuple(agent_names)  # type: ignore[assignment]
        self._sorted_agent_names: list[str] = sorted(self._agent_names)
        self._worker_id = int(worker_id)
        self._no_graphics = bool(no_graphics)
        self._seed = int(seed)
        self._time_scale = float(time_scale)
        self._timeout_wait = float(timeout_wait)

        self._text_channel = _make_text_obs_side_channel()
        self._engine_channel = EngineConfigurationChannel()
        self._engine_channel.set_configuration_parameters(
            time_scale=self._time_scale,
        )

        self._env: "UnityEnvironment" = UnityEnvironment(
            file_name=build_path,
            worker_id=self._worker_id,
            seed=self._seed,
            no_graphics=self._no_graphics,
            timeout_wait=self._timeout_wait,
            side_channels=[self._text_channel, self._engine_channel],
        )

        # Filled in lazily by reset() once we know the behavior name and obs shape.
        self._behavior_name: str | None = None
        self._obs_dim: int | None = None
        self._agent_id_map: dict[str, int] = {}
        self._step: int = 0
        self._closed: bool = False

    # ------------------------------------------------------------------ helpers
    def _select_behavior_name(self) -> str:
        """Return the (single) behavior name registered by the Unity build."""

        specs = self._env.behavior_specs
        names = list(specs.keys())
        if len(names) == 0:
            raise RuntimeError(
                "Unity environment exposed no behaviors. Did you forget to "
                "attach a ChefAgent with a Behavior Parameters component?"
            )
        if len(names) > 1:
            raise RuntimeError(
                "Unity environment exposed multiple behaviors "
                f"({names!r}); UnityOvercookedEnv assumes exactly one."
            )
        return names[0]

    def _refresh_agent_id_map(self, decision_agent_ids: list[int]) -> None:
        """Align our string agent names with Unity-issued integer agent_ids.

        We sort both sides to get a deterministic, order-agnostic mapping.
        """

        sorted_unity_ids = sorted(int(aid) for aid in decision_agent_ids)
        if len(sorted_unity_ids) != len(self._sorted_agent_names):
            raise RuntimeError(
                "Unity reported "
                f"{len(sorted_unity_ids)} decision-requesting agents but "
                f"agent_names has {len(self._sorted_agent_names)} entries."
            )
        self._agent_id_map = {
            name: aid
            for name, aid in zip(self._sorted_agent_names, sorted_unity_ids)
        }

    def _get_steps(self) -> tuple[Any, Any]:
        assert self._behavior_name is not None
        return self._env.get_steps(self._behavior_name)

    def _row_for_agent(
        self,
        decision_steps: Any,
        terminal_steps: Any,
        unity_agent_id: int,
    ) -> tuple[np.ndarray, float, bool]:
        """Return ``(obs_vector, reward, terminated)`` for one agent."""

        if unity_agent_id in terminal_steps.agent_id:
            idx = int(np.where(terminal_steps.agent_id == unity_agent_id)[0][0])
            obs_vec = np.asarray(terminal_steps.obs[0][idx], dtype=np.float32)
            reward = float(terminal_steps.reward[idx])
            return obs_vec, reward, True
        idx = int(np.where(decision_steps.agent_id == unity_agent_id)[0][0])
        obs_vec = np.asarray(decision_steps.obs[0][idx], dtype=np.float32)
        reward = float(decision_steps.reward[idx])
        return obs_vec, reward, False

    def _build_observation(
        self,
        decision_steps: Any,
        terminal_steps: Any,
    ) -> tuple[EnvObservation, dict[str, float], bool]:
        """Assemble the per-agent observation, rewards, and terminated flag."""

        raw: dict[str, np.ndarray] = {}
        rewards: dict[str, float] = {}
        terminated = False
        for name in self._agent_names:
            unity_id = self._agent_id_map[name]
            obs_vec, reward, term = self._row_for_agent(
                decision_steps, terminal_steps, unity_id
            )
            raw[name] = obs_vec
            rewards[name] = reward
            terminated = terminated or term

        text = self._text_channel.last_text or ""
        info: dict[str, Any] = {
            "behavior_name": self._behavior_name,
            "agent_id_map": dict(self._agent_id_map),
            "step": self._step,
        }
        return EnvObservation(raw=raw, text=text, info=info), rewards, terminated

    # --------------------------------------------------------------------- API
    def reset(self, seed: int | None = None) -> EnvObservation:
        if self._closed:
            raise RuntimeError("UnityOvercookedEnv is closed; create a new instance.")
        # ML-Agents UnityEnvironment.reset() does not accept a seed once
        # constructed; the seed argument exists to match the abstract API.
        del seed

        self._env.reset()
        self._behavior_name = self._select_behavior_name()
        decision_steps, terminal_steps = self._get_steps()

        if len(decision_steps) == 0:
            raise RuntimeError(
                "Unity reset() produced no decision_steps. The agents may be "
                "in a terminal state at the start of the episode."
            )

        # Infer obs dim from the first observation branch.
        first_obs_branch = decision_steps.obs[0]
        self._obs_dim = int(np.asarray(first_obs_branch).shape[-1])
        self._step = 0
        self._refresh_agent_id_map(list(decision_steps.agent_id))

        env_obs, _rewards, _term = self._build_observation(
            decision_steps, terminal_steps
        )
        return env_obs

    def step(self, actions: dict[str, int]) -> EnvStep:
        if self._closed:
            raise RuntimeError("UnityOvercookedEnv is closed; create a new instance.")
        if self._behavior_name is None:
            raise RuntimeError("step() called before reset(); call reset() first.")

        from mlagents_envs.base_env import ActionTuple

        # Build a [n_agents, 1] discrete action array, ordered by Unity agent_id
        # (ascending) to match the convention ML-Agents uses for set_actions.
        decision_steps, _ = self._get_steps()
        ordered_unity_ids = list(decision_steps.agent_id)
        # The previous decision_steps may not include all agent_ids (e.g. if an
        # agent just terminated). We expect both agents to be present at every
        # decision step in this env.
        if len(ordered_unity_ids) != len(self._agent_names):
            raise RuntimeError(
                "Unity reports "
                f"{len(ordered_unity_ids)} decision agents this step but "
                f"actions were supplied for {len(self._agent_names)}."
            )

        # Build name -> action lookup, then emit actions in the order
        # ML-Agents expects (the existing decision_steps.agent_id ordering).
        name_to_unity = self._agent_id_map
        unity_to_name = {v: k for k, v in name_to_unity.items()}
        discrete = np.zeros((len(ordered_unity_ids), 1), dtype=np.int32)
        for row, unity_id in enumerate(ordered_unity_ids):
            name = unity_to_name[int(unity_id)]
            discrete[row, 0] = int(actions[name])

        action_tuple = ActionTuple(discrete=discrete)
        self._env.set_actions(self._behavior_name, action_tuple)
        self._env.step()
        self._step += 1

        decision_steps, terminal_steps = self._get_steps()
        env_obs, rewards, terminated = self._build_observation(
            decision_steps, terminal_steps
        )
        # ML-Agents has no notion of "truncated" separate from "terminated"
        # at the side-channel level; the Unity side decides when to call
        # EndEpisode(). We surface terminated=True on terminal_steps and let
        # higher layers infer truncation from step count if they need to.
        truncated = False
        info: dict[str, Any] = {
            "behavior_name": self._behavior_name,
            "agent_id_map": dict(self._agent_id_map),
            "step": self._step,
        }
        return EnvStep(
            obs=env_obs,
            rewards=rewards,
            terminated=terminated,
            truncated=truncated,
            info=info,
        )

    def render(self, mode: str = "rgb_array") -> np.ndarray | None:
        # Unity owns the on-screen rendering; ML-Agents does not expose pixel
        # buffers through the Python API by default.
        del mode
        return None

    @property
    def agent_ids(self) -> list[str]:
        return list(self._agent_names)

    @property
    def action_space_size(self) -> int:
        # Must match ChefAgent.cs discrete branch size.
        return 7

    @property
    def obs_dim(self) -> int:
        if self._obs_dim is None:
            raise RuntimeError(
                "obs_dim is unknown until reset() has been called at least once."
            )
        return self._obs_dim

    def close(self) -> None:
        if self._closed:
            return
        try:
            self._env.close()
        finally:
            self._closed = True
