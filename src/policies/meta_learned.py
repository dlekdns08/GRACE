"""Learned meta-policy (DESIGN section 4.5 — main research contribution).

The meta-decision is local in time: should we call the LLM *now*, given the
current observation, the active subgoal, and how long since the last call?
A two-layer MLP on a compact feature vector is the right capacity for the
binary skip/call output. The network is trained end-to-end with GRPO
(Group Relative Policy Optimization) — see :mod:`src.training.grpo_trainer`.

Design choices worth flagging:

* The feature vector concatenates the *mean* of per-agent raw observations
  (so the meta-policy never has to know how many agents there are) with
  three scalar context features. ``obs_dim + 3`` total inputs.
* `should_call_llm` stores a detached snapshot of the input features and
  the chosen action's log-probability. The detached features are the
  contract with the GRPO trainer — the trainer recomputes logits on those
  saved features so gradients flow.
* `set_eval(True)` switches sampling off (argmax) for deterministic
  evaluation; defaults to stochastic sampling so training-time rollouts
  explore.
"""

from __future__ import annotations

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F  # noqa: N812

from src.policies.base import MetaPolicy, PolicyContext


def _featurize(ctx: PolicyContext) -> np.ndarray:
    """Build the feature vector for the meta-policy.

    Layout (concatenation; size depends on env's per-agent ``obs_dim``):
      - mean of agents' raw observations            (obs_dim floats)
      - subgoal_active flag                         (1 float)
      - steps_since_llm_call (clipped+normalized)   (1 float)
      - episode_step / 400 (capped at 1.0)          (1 float)

    Total: ``obs_dim + 3``.
    """
    raws = list(ctx.obs.raw.values())
    if not raws:
        raise ValueError("PolicyContext.obs.raw must contain at least one agent observation")
    obs_mean = np.mean(np.stack(raws, axis=0), axis=0).astype(np.float32)
    sg_active = 1.0 if ctx.current_subgoal is not None else 0.0
    steps_norm = float(min(int(ctx.steps_since_llm_call), 200)) / 200.0
    ep_norm = float(min(int(ctx.episode_step), 400)) / 400.0
    extras = np.array([sg_active, steps_norm, ep_norm], dtype=np.float32)
    return np.concatenate([obs_mean, extras], axis=0)


class LearnedMetaPolicy(MetaPolicy, nn.Module):
    """Small MLP outputting :math:`P(\\text{call})` over {skip, call}.

    Trained with GRPO (group-relative policy optimization). Why an MLP and
    not a transformer: the meta decision is local in time. A 2-layer MLP
    on (obs_summary, subgoal_active, time_since_call, episode_step) is the
    right capacity for a binary decision (DESIGN section 4.5).
    """

    def __init__(
        self,
        obs_dim: int,
        hidden_dim: int = 64,
        device: str = "cpu",
    ) -> None:
        nn.Module.__init__(self)
        MetaPolicy.__init__(self)

        if obs_dim <= 0:
            raise ValueError("obs_dim must be positive")
        if hidden_dim <= 0:
            raise ValueError("hidden_dim must be positive")

        self.obs_dim: int = int(obs_dim)
        self.hidden_dim: int = int(hidden_dim)
        self.input_dim: int = int(obs_dim) + 3
        self.net: nn.Sequential = nn.Sequential(
            nn.Linear(self.input_dim, self.hidden_dim),
            nn.ReLU(),
            nn.Linear(self.hidden_dim, self.hidden_dim),
            nn.ReLU(),
            nn.Linear(self.hidden_dim, 2),  # 0=skip, 1=call
        )
        self.device: torch.device = torch.device(device)
        self.to(self.device)

        # Mutable per-step state read by the rollout / GRPO trainer.
        self.last_logp: torch.Tensor | None = None
        self.last_features: torch.Tensor | None = None
        self.last_action: int = 0
        self.last_decision: bool = False
        self._eval_mode: bool = False

    # ------------------------------------------------------------------ helpers
    def set_eval(self, eval_mode: bool = True) -> None:
        """Toggle deterministic argmax decoding (eval) vs sampling (training)."""
        self._eval_mode = bool(eval_mode)

    # -------------------------------------------------------------- forward pass
    def forward(self, feat: torch.Tensor) -> torch.Tensor:
        """Return logits ``[B, 2]`` (or ``[2]`` for a 1-D input)."""
        return self.net(feat)

    # --------------------------------------------------------------- meta-policy
    def should_call_llm(self, ctx: PolicyContext) -> bool:
        """Decide whether to call the LLM at this step. Returns plain ``bool``."""
        feat_np = _featurize(ctx)
        feat = torch.from_numpy(feat_np).to(self.device)
        with torch.no_grad():
            logits = self.net(feat)
            if self._eval_mode:
                action = int(torch.argmax(logits, dim=-1).item())
            else:
                dist = torch.distributions.Categorical(logits=logits)
                action = int(dist.sample().item())
            log_probs = F.log_softmax(logits, dim=-1)
            self.last_logp = log_probs[action].detach()
        self.last_features = feat.detach()
        self.last_action = int(action)
        self.last_decision = action == 1
        return bool(self.last_decision)

    def reset(self) -> None:
        """Clear per-episode state."""
        self.last_logp = None
        self.last_features = None
        self.last_action = 0
        self.last_decision = False
