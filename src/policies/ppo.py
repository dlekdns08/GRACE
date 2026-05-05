"""Multi-agent PPO actor-critic with parameter sharing across agents.

The same trunk is applied independently to each agent's per-agent
observation; this is the standard "decentralized execution with shared
weights" recipe. Optionally the network can be conditioned on a
one-hot encoded subgoal vector (see DESIGN section 4.5 — the LLM-augmented
variant is the same network with `use_subgoal=True`).

Implementation notes:
  - The action distribution is `torch.distributions.Categorical`.
  - Policy head is initialised with ``gain=0.01`` (PPO best practice from
    Engstrom et al. 2020) so initial action distributions are near-uniform.
  - Value head is initialised with ``gain=1.0``.
  - `act` caches per-agent ``log_prob`` and ``value`` on
    ``self.last_step_cache`` keyed by agent id so the rollout loop can
    extract them post-hoc without re-running the forward pass.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F  # noqa: N812

from src.policies.base import Policy, PolicyContext

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass


_ACTIVATIONS: dict[str, type[nn.Module]] = {
    "tanh": nn.Tanh,
    "relu": nn.ReLU,
    "gelu": nn.GELU,
}


def _orthogonal_init(layer: nn.Linear, gain: float) -> None:
    nn.init.orthogonal_(layer.weight, gain=gain)
    nn.init.zeros_(layer.bias)


class PPOPolicy(Policy, nn.Module):
    """Shared-weights multi-agent PPO actor-critic.

    The trunk is an MLP. The actor head produces logits over the
    `action_dim` discrete actions; the critic head produces a scalar
    state-value. Per-agent observations (and optional subgoal one-hot)
    are stacked along the batch dimension for batched forward passes.
    """

    def __init__(
        self,
        obs_dim: int,
        action_dim: int,
        hidden_dim: int = 128,
        n_layers: int = 2,
        activation: str = "tanh",
        learning_rate: float = 3e-4,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_range: float = 0.2,
        value_coef: float = 0.5,
        entropy_coef: float = 0.01,
        n_epochs: int = 4,
        minibatch_size: int = 256,
        max_grad_norm: float = 0.5,
        use_subgoal: bool = False,
        subgoal_dim: int = 0,
        device: str = "cpu",
    ) -> None:
        nn.Module.__init__(self)
        if use_subgoal and subgoal_dim <= 0:
            raise ValueError("use_subgoal=True requires subgoal_dim > 0")

        self.obs_dim = int(obs_dim)
        self.action_dim = int(action_dim)
        self.hidden_dim = int(hidden_dim)
        self.n_layers = int(n_layers)
        self.activation_name = activation
        self.use_subgoal = bool(use_subgoal)
        self.subgoal_dim = int(subgoal_dim) if self.use_subgoal else 0

        # PPO hyperparameters — owned by the trainer but stored here for
        # configuration locality.
        self.learning_rate = float(learning_rate)
        self.gamma = float(gamma)
        self.gae_lambda = float(gae_lambda)
        self.clip_range = float(clip_range)
        self.value_coef = float(value_coef)
        self.entropy_coef = float(entropy_coef)
        self.n_epochs = int(n_epochs)
        self.minibatch_size = int(minibatch_size)
        self.max_grad_norm = float(max_grad_norm)

        if activation not in _ACTIVATIONS:
            raise ValueError(f"Unknown activation '{activation}'")
        act_cls = _ACTIVATIONS[activation]

        in_dim = self.obs_dim + self.subgoal_dim
        layers: list[nn.Module] = []
        prev = in_dim
        for _ in range(self.n_layers):
            linear = nn.Linear(prev, self.hidden_dim)
            _orthogonal_init(linear, gain=float(np.sqrt(2.0)))
            layers.append(linear)
            layers.append(act_cls())
            prev = self.hidden_dim
        self.trunk = nn.Sequential(*layers)

        self.policy_head = nn.Linear(self.hidden_dim, self.action_dim)
        _orthogonal_init(self.policy_head, gain=0.01)

        self.value_head = nn.Linear(self.hidden_dim, 1)
        _orthogonal_init(self.value_head, gain=1.0)

        self.device = torch.device(device)
        self.to(self.device)

        # Per-agent cache of (log_prob, value) for the most recent `act` call.
        # Filled in by `act`, consumed by the rollout collector.
        self.last_step_cache: dict[str, dict[str, float]] = {}

        # When False, `act` falls back to argmax (deterministic eval).
        self._sampling: bool = True

    # ------------------------------------------------------------------ helpers
    def set_sampling(self, sampling: bool) -> None:
        """Toggle between sample-from-distribution (training) and argmax (eval)."""
        self._sampling = bool(sampling)

    def _to_tensor(self, x: np.ndarray) -> torch.Tensor:
        return torch.as_tensor(x, dtype=torch.float32, device=self.device)

    def _build_input(
        self, obs: torch.Tensor, subgoal_oh: torch.Tensor | None
    ) -> torch.Tensor:
        if not self.use_subgoal:
            return obs
        if subgoal_oh is None:
            # Treat "no subgoal" as a zero vector — the same encoding produced
            # by `subgoal_to_onehot(None)`.
            zeros = torch.zeros(
                obs.shape[0], self.subgoal_dim, dtype=obs.dtype, device=obs.device
            )
            return torch.cat([obs, zeros], dim=-1)
        return torch.cat([obs, subgoal_oh], dim=-1)

    # ---------------------------------------------------------------- forward
    def forward(
        self, obs: torch.Tensor, subgoal_oh: torch.Tensor | None = None
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Return ``(logits [B, action_dim], value [B])`` for a batch of obs."""
        x = self._build_input(obs, subgoal_oh)
        h = self.trunk(x)
        logits = self.policy_head(h)
        value = self.value_head(h).squeeze(-1)
        return logits, value

    # --------------------------------------------------------------------- act
    def act(self, ctx: PolicyContext) -> dict[str, int]:
        """Sample one action per agent and cache (log_prob, value) per agent."""
        agent_ids = sorted(ctx.obs.raw.keys())
        obs_batch = np.stack([ctx.obs.raw[aid] for aid in agent_ids], axis=0)
        obs_t = self._to_tensor(obs_batch)

        subgoal_oh_t: torch.Tensor | None = None
        if self.use_subgoal:
            from src.training.rollout import subgoal_to_onehot  # local import: avoid cycle

            sg_dict = ctx.current_subgoal or {}
            sg_arr = np.stack(
                [subgoal_to_onehot(sg_dict.get(aid), self.subgoal_dim) for aid in agent_ids],
                axis=0,
            )
            subgoal_oh_t = self._to_tensor(sg_arr)

        with torch.no_grad():
            logits, values = self.forward(obs_t, subgoal_oh_t)
            dist = torch.distributions.Categorical(logits=logits)
            if self._sampling:
                actions = dist.sample()
            else:
                actions = logits.argmax(dim=-1)
            log_probs = dist.log_prob(actions)

        self.last_step_cache = {}
        out: dict[str, int] = {}
        for i, aid in enumerate(agent_ids):
            out[aid] = int(actions[i].item())
            self.last_step_cache[aid] = {
                "log_prob": float(log_probs[i].item()),
                "value": float(values[i].item()),
            }
        return out

    # ------------------------------------------------------------------ logits
    def get_logits(self, ctx: PolicyContext) -> torch.Tensor:
        """Per-agent action logits ``[n_agents, action_dim]`` for entropy meta-policies."""
        agent_ids = sorted(ctx.obs.raw.keys())
        obs_batch = np.stack([ctx.obs.raw[aid] for aid in agent_ids], axis=0)
        obs_t = self._to_tensor(obs_batch)

        subgoal_oh_t: torch.Tensor | None = None
        if self.use_subgoal:
            from src.training.rollout import subgoal_to_onehot  # local import: avoid cycle

            sg_dict = ctx.current_subgoal or {}
            sg_arr = np.stack(
                [subgoal_to_onehot(sg_dict.get(aid), self.subgoal_dim) for aid in agent_ids],
                axis=0,
            )
            subgoal_oh_t = self._to_tensor(sg_arr)

        with torch.no_grad():
            logits, _ = self.forward(obs_t, subgoal_oh_t)
        return logits

    # ---------------------------------------------------------------- evaluate
    def evaluate(
        self,
        obs: torch.Tensor,
        actions: torch.Tensor,
        subgoal_oh: torch.Tensor | None = None,
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """Return ``(log_prob, entropy, value)`` for a batch of (obs, action) pairs."""
        logits, values = self.forward(obs, subgoal_oh)
        dist = torch.distributions.Categorical(logits=logits)
        log_prob = dist.log_prob(actions)
        entropy = dist.entropy()
        return log_prob, entropy, values
