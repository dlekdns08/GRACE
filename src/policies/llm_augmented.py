"""LLM-augmented PPO policy (DESIGN sections 3.3, 4.5).

This is the action policy used in the "LLM in the loop" arm of every
experiment. It is structurally identical to :class:`PPOPolicy` — same
trunk, same actor and critic heads, same training procedure — with the
single addition that each agent's per-step input is concatenated with a
one-hot encoding of the LLM-supplied subgoal.

In Phase 2 :class:`PPOPolicy` itself was generalised to accept a
``use_subgoal`` flag and to read ``ctx.current_subgoal`` inside
:meth:`act` and :meth:`get_logits`, so this class does *not* need to
override any methods. It exists as a separate class for two reasons:

1. **Config clarity** — Hydra configs can target
   ``src.policies.llm_augmented.LLMAugmentedPPOPolicy`` to make it
   self-documenting that a given experiment uses subgoal conditioning.
2. **Defaults** — ``use_subgoal`` is forced ``True`` and ``subgoal_dim``
   defaults to the size of the closed subgoal enum
   (:data:`src.training.rollout.N_SUBGOAL_CLASSES`), so the config can
   omit them.
"""

from __future__ import annotations

from src.policies.ppo import PPOPolicy
from src.training.rollout import N_SUBGOAL_CLASSES


class LLMAugmentedPPOPolicy(PPOPolicy):
    """PPO actor-critic conditioned on a per-agent subgoal one-hot.

    The subgoal name comes from :attr:`PolicyContext.current_subgoal` and
    is encoded by :func:`src.training.rollout.subgoal_to_onehot` inside
    the parent :meth:`PPOPolicy.act`. Unknown / ``None`` subgoals encode
    as zero vectors, so partially specified or absent subgoals never
    crash the rollout.
    """

    def __init__(self, *args, subgoal_dim: int = N_SUBGOAL_CLASSES, **kwargs) -> None:
        # Force subgoal conditioning regardless of caller input.
        kwargs["use_subgoal"] = True
        kwargs["subgoal_dim"] = int(subgoal_dim)
        super().__init__(*args, **kwargs)
