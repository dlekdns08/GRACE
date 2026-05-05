"""Standard clipped-objective PPO trainer for the multi-agent setting.

Each per-agent transition is treated as a flat sample for the update —
parameter sharing means every agent's experience trains the same network.
GAE-Lambda advantages are computed *per agent* using the per-agent
reward / value / done sequence, then concatenated into one big batch.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import torch
import torch.nn as nn

from src.policies.ppo import PPOPolicy
from src.training.rollout import RolloutBatch, subgoal_to_onehot


def _to_dict(cfg: Any) -> dict:
    """Best-effort conversion of an OmegaConf or dict-like config to a plain dict."""
    if isinstance(cfg, dict):
        return dict(cfg)
    try:
        from omegaconf import OmegaConf  # local import: avoid hard dep at import time

        if hasattr(cfg, "_content") or OmegaConf.is_config(cfg):
            return OmegaConf.to_container(cfg, resolve=True)  # type: ignore[return-value]
    except ImportError:  # pragma: no cover - defensive
        pass
    return dict(cfg)  # may raise; intentional


class PPOTrainer:
    """Single-update PPO trainer wrapped around a :class:`PPOPolicy`.

    `update` consumes a :class:`RolloutBatch`, computes GAE advantages,
    and runs ``n_epochs * (batch_size // minibatch_size)`` SGD steps with
    the clipped surrogate objective + value loss + entropy bonus.
    """

    def __init__(self, policy: PPOPolicy, cfg: Any) -> None:
        self.policy = policy
        cfg_dict = _to_dict(cfg)

        self.gamma = float(cfg_dict.get("gamma", policy.gamma))
        self.gae_lambda = float(cfg_dict.get("gae_lambda", policy.gae_lambda))
        self.clip_range = float(cfg_dict.get("clip_range", policy.clip_range))
        self.value_coef = float(cfg_dict.get("value_coef", policy.value_coef))
        self.entropy_coef = float(cfg_dict.get("entropy_coef", policy.entropy_coef))
        self.n_epochs = int(cfg_dict.get("n_epochs", policy.n_epochs))
        self.minibatch_size = int(cfg_dict.get("minibatch_size", policy.minibatch_size))
        self.max_grad_norm = float(cfg_dict.get("max_grad_norm", policy.max_grad_norm))
        self.learning_rate = float(cfg_dict.get("learning_rate", policy.learning_rate))

        self.optimizer = torch.optim.Adam(policy.parameters(), lr=self.learning_rate)
        self.device = policy.device

    # --------------------------------------------------------- advantage computation
    def compute_advantages(
        self, batch: RolloutBatch
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """Compute GAE-Lambda advantages and returns over flattened per-agent samples.

        Returns ``(advantages, returns)`` each of shape ``[B * n_agents]`` where
        the per-agent ordering matches the order the rest of the trainer uses
        when flattening transitions (sorted agent ids).
        """
        if not batch.transitions:
            empty = torch.zeros(0, device=self.device)
            return empty, empty.clone()

        agent_ids = sorted(batch.transitions[0].obs_raw.keys())
        T = len(batch.transitions)
        n_agents = len(agent_ids)

        # Per-agent per-step buffers.
        rewards = np.zeros((n_agents, T), dtype=np.float32)
        values = np.zeros((n_agents, T), dtype=np.float32)
        dones = np.zeros((n_agents, T), dtype=np.float32)

        for t, tr in enumerate(batch.transitions):
            for ai, aid in enumerate(agent_ids):
                rewards[ai, t] = float(tr.rewards.get(aid, 0.0))
                values[ai, t] = float(tr.values.get(aid, 0.0))
                dones[ai, t] = 1.0 if tr.done else 0.0

        advantages = np.zeros_like(rewards)
        last_gae = np.zeros((n_agents,), dtype=np.float32)
        for t in reversed(range(T)):
            if t == T - 1:
                next_value = np.zeros((n_agents,), dtype=np.float32)
            else:
                next_value = values[:, t + 1]
            non_terminal = 1.0 - dones[:, t]
            delta = rewards[:, t] + self.gamma * next_value * non_terminal - values[:, t]
            last_gae = delta + self.gamma * self.gae_lambda * non_terminal * last_gae
            advantages[:, t] = last_gae

        returns = advantages + values

        # Flatten in (agent, time) order so other tensors must follow the same convention.
        adv_flat = torch.as_tensor(advantages.reshape(-1), dtype=torch.float32, device=self.device)
        ret_flat = torch.as_tensor(returns.reshape(-1), dtype=torch.float32, device=self.device)
        return adv_flat, ret_flat

    # --------------------------------------------------------------------- update
    def _flatten_batch(
        self, batch: RolloutBatch
    ) -> tuple[
        torch.Tensor,  # obs   [N, obs_dim]
        torch.Tensor,  # actions [N]
        torch.Tensor,  # old_log_probs [N]
        torch.Tensor,  # old_values [N]
        torch.Tensor | None,  # subgoal_oh [N, subgoal_dim] or None
    ]:
        agent_ids = sorted(batch.transitions[0].obs_raw.keys())
        T = len(batch.transitions)
        n_agents = len(agent_ids)
        obs_dim = self.policy.obs_dim

        obs_arr = np.zeros((n_agents, T, obs_dim), dtype=np.float32)
        act_arr = np.zeros((n_agents, T), dtype=np.int64)
        logp_arr = np.zeros((n_agents, T), dtype=np.float32)
        val_arr = np.zeros((n_agents, T), dtype=np.float32)

        if self.policy.use_subgoal:
            sg_arr = np.zeros((n_agents, T, self.policy.subgoal_dim), dtype=np.float32)
        else:
            sg_arr = None  # type: ignore[assignment]

        for t, tr in enumerate(batch.transitions):
            for ai, aid in enumerate(agent_ids):
                obs_arr[ai, t] = tr.obs_raw[aid]
                act_arr[ai, t] = int(tr.actions[aid])
                logp_arr[ai, t] = float(tr.log_probs.get(aid, 0.0))
                val_arr[ai, t] = float(tr.values.get(aid, 0.0))
                if sg_arr is not None:
                    if tr.subgoal_oh is not None and aid in tr.subgoal_oh:
                        sg_arr[ai, t] = tr.subgoal_oh[aid]
                    elif tr.subgoal is not None:
                        sg_arr[ai, t] = subgoal_to_onehot(
                            tr.subgoal.get(aid), self.policy.subgoal_dim
                        )

        obs_t = torch.as_tensor(obs_arr.reshape(-1, obs_dim), dtype=torch.float32, device=self.device)
        act_t = torch.as_tensor(act_arr.reshape(-1), dtype=torch.long, device=self.device)
        logp_t = torch.as_tensor(logp_arr.reshape(-1), dtype=torch.float32, device=self.device)
        val_t = torch.as_tensor(val_arr.reshape(-1), dtype=torch.float32, device=self.device)
        sg_t: torch.Tensor | None = None
        if sg_arr is not None:
            sg_t = torch.as_tensor(
                sg_arr.reshape(-1, self.policy.subgoal_dim),
                dtype=torch.float32,
                device=self.device,
            )

        return obs_t, act_t, logp_t, val_t, sg_t

    def update(self, batch: RolloutBatch) -> dict[str, float]:
        """One PPO update pass over ``batch``. Returns averaged metrics."""
        if not batch.transitions:
            return {
                "policy_loss": 0.0,
                "value_loss": 0.0,
                "entropy": 0.0,
                "approx_kl": 0.0,
                "clip_frac": 0.0,
                "n_samples": 0,
            }

        obs_t, act_t, old_logp_t, _old_val_t, sg_t = self._flatten_batch(batch)
        adv_t, ret_t = self.compute_advantages(batch)

        # Normalize advantages within this batch.
        if adv_t.numel() > 1:
            adv_t = (adv_t - adv_t.mean()) / (adv_t.std(unbiased=False) + 1e-8)

        n_samples = obs_t.shape[0]
        minibatch_size = min(self.minibatch_size, n_samples)

        policy_losses: list[float] = []
        value_losses: list[float] = []
        entropies: list[float] = []
        approx_kls: list[float] = []
        clip_fracs: list[float] = []

        rng = np.random.default_rng()
        for _ in range(self.n_epochs):
            indices = rng.permutation(n_samples)
            for start in range(0, n_samples, minibatch_size):
                mb_idx = indices[start : start + minibatch_size]
                if len(mb_idx) == 0:
                    continue
                idx_t = torch.as_tensor(mb_idx, dtype=torch.long, device=self.device)
                mb_obs = obs_t.index_select(0, idx_t)
                mb_act = act_t.index_select(0, idx_t)
                mb_old_logp = old_logp_t.index_select(0, idx_t)
                mb_adv = adv_t.index_select(0, idx_t)
                mb_ret = ret_t.index_select(0, idx_t)
                mb_sg = sg_t.index_select(0, idx_t) if sg_t is not None else None

                logp, entropy, value = self.policy.evaluate(mb_obs, mb_act, mb_sg)
                ratio = torch.exp(logp - mb_old_logp)
                unclipped = ratio * mb_adv
                clipped = torch.clamp(ratio, 1.0 - self.clip_range, 1.0 + self.clip_range) * mb_adv
                policy_loss = -torch.min(unclipped, clipped).mean()
                value_loss = 0.5 * (value - mb_ret).pow(2).mean()
                entropy_mean = entropy.mean()
                loss = (
                    policy_loss
                    + self.value_coef * value_loss
                    - self.entropy_coef * entropy_mean
                )

                self.optimizer.zero_grad()
                loss.backward()
                if self.max_grad_norm > 0:
                    nn.utils.clip_grad_norm_(self.policy.parameters(), self.max_grad_norm)
                self.optimizer.step()

                with torch.no_grad():
                    approx_kl = (mb_old_logp - logp).mean()
                    clip_frac = ((ratio - 1.0).abs() > self.clip_range).float().mean()

                policy_losses.append(float(policy_loss.item()))
                value_losses.append(float(value_loss.item()))
                entropies.append(float(entropy_mean.item()))
                approx_kls.append(float(approx_kl.item()))
                clip_fracs.append(float(clip_frac.item()))

        def _mean(xs: list[float]) -> float:
            return float(np.mean(xs)) if xs else 0.0

        return {
            "policy_loss": _mean(policy_losses),
            "value_loss": _mean(value_losses),
            "entropy": _mean(entropies),
            "approx_kl": _mean(approx_kls),
            "clip_frac": _mean(clip_fracs),
            "n_samples": float(n_samples),
        }
