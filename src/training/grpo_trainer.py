"""GRPO (Group Relative Policy Optimization) trainer for the meta-policy.

DESIGN section 4.5 specifies that the meta-policy is trained group-wise:
the same initial state is rolled out ``K`` times, each rollout reuses the
*same* (frozen) action policy but a fresh stochastic sample from the
meta-policy. The reward attached to a rollout is the env return minus a
per-call penalty :math:`\\lambda`, encouraging the meta-policy to call only
when the call pays for itself in environment return.

Algorithm summary:

1. Collect a group of ``K`` rollouts. Each rollout records, *for every env
   step*, the meta-policy feature vector and the action it took (call or
   skip).
2. Compute per-rollout score :math:`R_i = \\sum r_t - \\lambda \\cdot
   n_\\text{calls}^i`.
3. Standardize across the group: :math:`A_i = (R_i - \\bar R) / (\\sigma_R +
   \\epsilon)`. This is the GRPO trick — no learned value baseline needed.
4. Loss: :math:`-\\mathbb{E}_i [A_i \\cdot \\sum_t \\log\\pi(a_t | s_t)]`,
   plus a KL penalty against a periodically refreshed snapshot of the
   meta-policy to prevent runaway updates.

Note on gradients: the rollout stores *detached* features and actions. The
update path here recomputes logits on those features so autograd actually
has a graph to differentiate. We never differentiate through the env or
through the action policy — only through the meta-policy's own forward
pass.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import torch
import torch.nn.functional as F  # noqa: N812

from src.envs import EnvObservation, OvercookedEnv
from src.llm import (
    LLMClient,
    LLMResponse,
    build_request,
    parse_subgoal,
)
from src.policies.base import Policy, PolicyContext
from src.policies.meta_learned import LearnedMetaPolicy, _featurize


# ----------------------------------------------------------------------- data classes
@dataclass(slots=True)
class MetaDecision:
    """One meta-policy decision point inside a rollout.

    `features` is the input vector the policy saw (the same array
    :func:`src.policies.meta_learned._featurize` produced); `action` is the
    sampled binary action (0=skip, 1=call). `logp` is captured for
    diagnostics but not used in the GRPO update — we recompute it from the
    current network parameters during :meth:`GRPOTrainer.update`.
    """

    features: np.ndarray
    action: int
    logp: float = 0.0


@dataclass(slots=True)
class MetaRollout:
    """One rollout's worth of meta decisions plus its scalar score."""

    decisions: list[MetaDecision]
    total_reward: float
    n_llm_calls: int
    extras: dict[str, Any] = field(default_factory=dict)


# ----------------------------------------------------------------------- helpers
def _sum_rewards(rewards: dict[str, float]) -> float:
    return float(sum(rewards.values()))


def _kl_against(
    logits: torch.Tensor, ref_logits: torch.Tensor
) -> torch.Tensor:
    """Forward KL(:math:`\\pi || \\pi_\\text{ref}`) on logits ``[N, 2]``.

    Per-row KL averaged over rows. Matches the standard GRPO formulation.
    """
    log_p = F.log_softmax(logits, dim=-1)
    log_q = F.log_softmax(ref_logits, dim=-1)
    p = log_p.exp()
    return (p * (log_p - log_q)).sum(dim=-1).mean()


# ----------------------------------------------------------------------- rollout helper
def collect_meta_rollout(
    env: OvercookedEnv,
    action_policy: Policy,
    meta_policy: LearnedMetaPolicy,
    llm_client: LLMClient,
    max_steps: int,
    seed: int | None = None,
) -> MetaRollout:
    """Collect a single rollout while logging *every* meta-policy decision.

    Differs from :func:`src.training.rollout.collect_rollout` in two ways:

    1. Records a :class:`MetaDecision` on **every** step, not only on
       steps where the LLM was called. GRPO needs the full action sequence.
    2. Returns a flat :class:`MetaRollout` (no per-agent transitions). The
       env return is summed across agents and across the episode; the
       caller decides how to penalize calls.

    The meta-policy is run in *stochastic* (sampling) mode: GRPO needs
    on-policy variance across the group.
    """
    if max_steps <= 0:
        raise ValueError("max_steps must be positive")

    # Force stochastic sampling — GRPO is on-policy.
    prev_eval = meta_policy._eval_mode
    meta_policy.set_eval(False)
    meta_policy.reset()

    decisions: list[MetaDecision] = []
    total_reward = 0.0
    n_llm_calls = 0

    obs: EnvObservation = env.reset(seed=seed)
    current_subgoal: dict[str, str] | None = None
    steps_since_call = 0
    episode_step = 0
    agent_ids = list(env.agent_ids)

    try:
        for _ in range(max_steps):
            ctx = PolicyContext(
                obs=obs,
                current_subgoal=current_subgoal,
                steps_since_llm_call=steps_since_call,
                episode_step=episode_step,
            )

            # 1) meta decision (always recorded)
            decision = bool(meta_policy.should_call_llm(ctx))
            assert meta_policy.last_features is not None
            decisions.append(
                MetaDecision(
                    features=meta_policy.last_features.detach().cpu().numpy().copy(),
                    action=int(meta_policy.last_action),
                    logp=float(meta_policy.last_logp.item())
                    if meta_policy.last_logp is not None
                    else 0.0,
                )
            )

            # 2) optional LLM call
            llm_called_this_step = False
            if decision:
                req = build_request(ctx.obs.text, agent_ids)
                response: LLMResponse = llm_client.call(req)
                parsed = parse_subgoal(response.text)
                if parsed is not None:
                    current_subgoal = parsed
                steps_since_call = 0
                n_llm_calls += 1
                llm_called_this_step = True

            if not llm_called_this_step:
                steps_since_call += 1

            # 3) action policy
            actions = action_policy.act(ctx)

            # 4) env step
            env_step = env.step(actions)
            total_reward += _sum_rewards(env_step.rewards)
            episode_step += 1
            obs = env_step.obs

            if env_step.terminated or env_step.truncated:
                break
    finally:
        meta_policy.set_eval(prev_eval)

    return MetaRollout(
        decisions=decisions,
        total_reward=float(total_reward),
        n_llm_calls=int(n_llm_calls),
    )


# ----------------------------------------------------------------------- trainer
class GRPOTrainer:
    """Group Relative Policy Optimization for the learned meta-policy."""

    def __init__(
        self,
        meta_policy: LearnedMetaPolicy,
        learning_rate: float = 3e-4,
        call_cost: float = 0.01,
        kl_coef: float = 0.02,
        group_size: int = 8,
        max_grad_norm: float = 0.5,
    ) -> None:
        if group_size <= 0:
            raise ValueError("group_size must be positive")
        self.meta: LearnedMetaPolicy = meta_policy
        self.optimizer: torch.optim.Optimizer = torch.optim.Adam(
            meta_policy.parameters(), lr=float(learning_rate)
        )
        self.learning_rate: float = float(learning_rate)
        self.call_cost: float = float(call_cost)
        self.kl_coef: float = float(kl_coef)
        self.group_size: int = int(group_size)
        self.max_grad_norm: float = float(max_grad_norm)
        # KL reference: a frozen snapshot of the meta network. Refreshed
        # explicitly via :meth:`update_reference`.
        self._ref: torch.nn.Module = (
            copy.deepcopy(meta_policy.net).requires_grad_(False)
        )
        self._ref.eval()

    # ----------------------------------------------------------------- ref refresh
    def update_reference(self) -> None:
        """Refresh the KL reference snapshot. Call periodically."""
        self._ref = copy.deepcopy(self.meta.net).requires_grad_(False)
        self._ref.eval()

    # --------------------------------------------------------------------- update
    def update(self, group: list[MetaRollout]) -> dict[str, float]:
        """One GRPO update over a group of rollouts.

        The group must contain at least 1 rollout (and ideally
        :attr:`group_size`). Empty groups or groups with no decisions are
        a no-op that still returns a metrics dict so the caller can log
        zero-valued iterations uniformly.
        """
        if not group:
            return {
                "policy_loss": 0.0,
                "kl": 0.0,
                "mean_R": 0.0,
                "std_R": 0.0,
                "mean_calls": 0.0,
                "n_decisions": 0.0,
                "n_groups": 0.0,
            }

        device = next(self.meta.parameters()).device

        # 1) per-rollout scores
        raw_returns = np.array(
            [r.total_reward for r in group], dtype=np.float32
        )
        n_calls = np.array([r.n_llm_calls for r in group], dtype=np.float32)
        scores = raw_returns - self.call_cost * n_calls
        mean_R = float(scores.mean())
        std_R = float(scores.std())

        # 2) group-relative advantages (broadcast across the rollout's
        # decisions). Single-rollout group → zero advantage; gradient is 0
        # but we still compute a KL term to keep the call shape uniform.
        advantages = (scores - mean_R) / (std_R + 1e-8)

        # 3) flatten decisions and pair each with its rollout's advantage
        all_features: list[np.ndarray] = []
        all_actions: list[int] = []
        all_advantages: list[float] = []
        for adv, rollout in zip(advantages.tolist(), group, strict=False):
            for dec in rollout.decisions:
                all_features.append(np.asarray(dec.features, dtype=np.float32))
                all_actions.append(int(dec.action))
                all_advantages.append(float(adv))

        n_decisions = len(all_features)
        if n_decisions == 0:
            return {
                "policy_loss": 0.0,
                "kl": 0.0,
                "mean_R": mean_R,
                "std_R": std_R,
                "mean_calls": float(n_calls.mean()),
                "n_decisions": 0.0,
                "n_groups": float(len(group)),
            }

        feat_t = torch.as_tensor(
            np.stack(all_features, axis=0), dtype=torch.float32, device=device
        )
        act_t = torch.as_tensor(all_actions, dtype=torch.long, device=device)
        adv_t = torch.as_tensor(all_advantages, dtype=torch.float32, device=device)

        # 4) recompute logits with grad enabled, gather log_prob of taken action
        logits = self.meta.net(feat_t)  # [N, 2]
        log_probs = F.log_softmax(logits, dim=-1)
        chosen_logp = log_probs.gather(1, act_t.unsqueeze(-1)).squeeze(-1)  # [N]

        # 5) policy loss = - mean(advantage * logp). Sum within rollout, mean over rollouts
        # is equivalent to mean over decisions when advantage is broadcast (length already
        # accounts for per-decision contribution). We use mean over decisions for stability.
        policy_loss = -(adv_t * chosen_logp).mean()

        # 6) KL to reference
        with torch.no_grad():
            ref_logits = self._ref(feat_t)
        kl = _kl_against(logits, ref_logits)

        loss = policy_loss + self.kl_coef * kl

        self.optimizer.zero_grad()
        loss.backward()
        if self.max_grad_norm > 0:
            torch.nn.utils.clip_grad_norm_(
                self.meta.parameters(), self.max_grad_norm
            )
        self.optimizer.step()

        return {
            "policy_loss": float(policy_loss.detach().item()),
            "kl": float(kl.detach().item()),
            "mean_R": mean_R,
            "std_R": std_R,
            "mean_calls": float(n_calls.mean()),
            "n_decisions": float(n_decisions),
            "n_groups": float(len(group)),
        }


# Re-export the featurize helper for callers that want to mock decisions
# without going through the policy (used in tests).
__all__ = [
    "GRPOTrainer",
    "MetaDecision",
    "MetaRollout",
    "collect_meta_rollout",
    "_featurize",
]
