"""Heuristic meta-policies (DESIGN section 4.5).

The meta-policy decides *when* to call the LLM. Its interface is a single
boolean :meth:`MetaPolicy.should_call_llm`, which keeps it cleanly
swappable with the learned variant in :mod:`src.policies.meta_learned`.

This module contains the four reference heuristics used as baselines in
the experiment matrix:

* :class:`FixedKMetaPolicy` — call every ``k`` env steps. The classical
  SayCan / Plan-Seq-Learn convention; the simplest non-trivial baseline.
* :class:`NeverCallMetaPolicy` — never call. Equivalent to plain PPO with
  no LLM augmentation; useful as the absolute floor in ablation tables.
* :class:`AlwaysCallMetaPolicy` — call every step. The "unlimited LLM"
  reference. Caps the *upper bound* of LLM-induced gains so the learned
  meta-policy can be compared against both extremes.
* :class:`EntropyMetaPolicy` — call when the action policy is uncertain
  (high predictive entropy) AND a cooldown has elapsed since the last
  call. The first principled heuristic from DESIGN section 4.5: "ask the
  planner only when the local policy itself doesn't know what to do."
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.policies.base import MetaPolicy, Policy, PolicyContext

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass


class FixedKMetaPolicy(MetaPolicy):
    """Call the LLM every ``k`` environment steps (and at step 0).

    This is the canonical fixed-period baseline from DESIGN section 4.5.
    `k` controls the LLM-call budget; the experiment sweep uses several
    values to trace the cost-vs-performance frontier.
    """

    def __init__(self, k: int) -> None:
        if k <= 0:
            raise ValueError("k must be positive")
        self.k: int = int(k)
        self.last_decision: bool = False

    def should_call_llm(self, ctx: PolicyContext) -> bool:
        decision = (ctx.episode_step % self.k) == 0
        self.last_decision = decision
        return decision

    def reset(self) -> None:
        self.last_decision = False


class NeverCallMetaPolicy(MetaPolicy):
    """Never call the LLM. Used as the plain-PPO baseline."""

    def __init__(self) -> None:
        self.last_decision: bool = False

    def should_call_llm(self, ctx: PolicyContext) -> bool:
        self.last_decision = False
        return False

    def reset(self) -> None:
        self.last_decision = False


class AlwaysCallMetaPolicy(MetaPolicy):
    """Call the LLM every step. The 'unlimited LLM' reference baseline.

    Together with :class:`NeverCallMetaPolicy` it brackets the achievable
    range of LLM-conditioned PPO performance for any fixed prompt.
    """

    def __init__(self) -> None:
        self.last_decision: bool = False

    def should_call_llm(self, ctx: PolicyContext) -> bool:
        self.last_decision = True
        return True

    def reset(self) -> None:
        self.last_decision = False


class EntropyMetaPolicy(MetaPolicy):
    """Call the LLM when the action policy's predictive entropy is high.

    Heuristic intuition (DESIGN section 4.5): the action policy already
    knows what to do in routine states, but its action distribution
    flattens out (entropy spikes) at decision points where multiple
    options look equally good. Those are exactly the moments where a
    high-level planner is worth its cost.

    A cooldown of ``min_steps_between`` env steps is enforced to avoid
    chains of redundant calls when the entropy briefly stays above the
    threshold for several consecutive steps. The bound to the action
    policy is established explicitly via :meth:`attach`; without an
    attached policy the meta-policy is silent (returns ``False``).
    """

    def __init__(self, threshold: float = 1.2, min_steps_between: int = 5) -> None:
        if min_steps_between < 0:
            raise ValueError("min_steps_between must be non-negative")
        self.threshold: float = float(threshold)
        self.min_steps_between: int = int(min_steps_between)
        # Sentinel below any plausible episode_step so the very first
        # check passes the cooldown gate.
        self._last_call_step: int = -(10**9)
        self.last_entropy: float | None = None
        self.last_decision: bool = False
        self._policy: Policy | None = None

    def attach(self, policy: Policy) -> None:
        """Bind to the action policy whose logits drive the decision."""
        self._policy = policy

    def should_call_llm(self, ctx: PolicyContext) -> bool:
        # Cooldown gate: never call within `min_steps_between` of a prior call.
        if ctx.episode_step - self._last_call_step < self.min_steps_between:
            self.last_decision = False
            return False

        policy = self._policy
        if policy is None:
            # Nothing attached → cannot read entropy → conservative no.
            self.last_decision = False
            return False

        logits = policy.get_logits(ctx)
        if logits is None:
            # Opaque policy (no differentiable logits) — refuse silently.
            self.last_decision = False
            return False

        # Local import: torch is heavy, and importing it lazily keeps the
        # module import cheap for environments where this class is unused.
        import torch

        with torch.no_grad():
            probs = logits.softmax(-1)
            ent_per_agent = -(probs * probs.clamp_min(1e-9).log()).sum(-1)
            entropy = ent_per_agent.mean()

        self.last_entropy = float(entropy.item())
        decision = self.last_entropy > self.threshold
        if decision:
            self._last_call_step = int(ctx.episode_step)
        self.last_decision = decision
        return decision

    def reset(self) -> None:
        self._last_call_step = -(10**9)
        self.last_entropy = None
        self.last_decision = False
