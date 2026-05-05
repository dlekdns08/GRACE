"""Hydra entry point for training the learned meta-policy with GRPO.

DESIGN section 4.5: the meta-policy is trained group-wise. For each
training iteration we collect ``group_size`` rollouts from the same
initial state with stochastic meta sampling, score each by
``return - call_cost * n_llm_calls``, and update the meta-policy with
group-relative advantages.

The action policy is held fixed during meta-policy training: a
preceding PPO phase produced it (or, for smoke tests, we instantiate a
fresh ``PPOPolicy`` because the dummy env doesn't need a trained policy
to exercise the GRPO pipeline).
"""

from __future__ import annotations

import logging
from pathlib import Path

import hydra
import torch
from hydra.core.hydra_config import HydraConfig
from omegaconf import DictConfig, OmegaConf

from src.envs import DummyOvercookedEnv, OvercookedEnv
from src.llm import PROMPT_VERSION, CachedLLMClient
from src.policies import PPOPolicy
from src.policies.meta_learned import LearnedMetaPolicy
from src.training.grpo_trainer import GRPOTrainer, collect_meta_rollout
from src.utils import RolloutLogger, save_resolved_config, seed_everything

_log = logging.getLogger(__name__)

# How often to refresh the GRPO KL reference snapshot, in groups.
_REF_REFRESH_INTERVAL = 50


def _instantiate(cfg_node: DictConfig, **kwargs):
    """Instantiate via `_target_`, dropping convention-only keys.

    Mirrors `scripts/train.py::_instantiate` but additionally strips the
    `training:` subkey from meta configs (which is not a constructor
    argument — the GRPO trainer reads it separately).
    """
    plain = OmegaConf.to_container(cfg_node, resolve=True)
    if not isinstance(plain, dict):
        raise TypeError(f"Expected dict-like config; got {type(plain).__name__}")
    plain = {k: v for k, v in plain.items() if k not in ("name", "training")}
    plain.update(kwargs)
    return hydra.utils.instantiate(plain, _recursive_=False)


def _make_env(cfg: DictConfig) -> OvercookedEnv:
    backend = cfg.env.backend
    if backend == "dummy":
        return DummyOvercookedEnv(max_steps=int(cfg.env.horizon))
    if backend == "python":
        from src.envs.python_env import PythonOvercookedEnv

        return PythonOvercookedEnv(layout=cfg.env.layout, horizon=int(cfg.env.horizon))
    if backend == "unity":
        from src.envs.unity_env import UnityOvercookedEnv  # type: ignore[import-not-found]

        return UnityOvercookedEnv(**cfg.env.get("unity", {}))
    raise ValueError(f"Unknown env.backend: {backend!r}")


def _resolve_run_dir(cfg: DictConfig) -> Path:
    try:
        hc = HydraConfig.get()
        return Path(hc.runtime.output_dir)
    except Exception:
        return Path.cwd()


def _make_action_policy(cfg: DictConfig, ckpt_path: str | None) -> PPOPolicy:
    """Instantiate and (optionally) load a frozen action policy.

    For smoke tests where ``ckpt_path`` is ``None`` we just return a fresh
    untrained policy — the GRPO pipeline only needs *some* action policy
    to step the env.
    """
    policy: PPOPolicy = _instantiate(
        cfg.policy,
        obs_dim=int(cfg.env.obs_dim),
        action_dim=int(cfg.env.action_dim),
    )
    if ckpt_path:
        state = torch.load(ckpt_path, map_location="cpu")
        if isinstance(state, dict) and "policy" in state:
            state = state["policy"]
        policy.load_state_dict(state)
    # Freeze: GRPO trains only the meta-policy.
    for p in policy.parameters():
        p.requires_grad_(False)
    policy.eval()
    return policy


@hydra.main(version_base=None, config_path="../configs", config_name="base")
def main(cfg: DictConfig) -> None:
    seed_everything(int(cfg.experiment.seed))
    run_dir = _resolve_run_dir(cfg)
    run_dir.mkdir(parents=True, exist_ok=True)
    save_resolved_config(cfg, run_dir / "config.yaml")

    if str(cfg.meta.get("name", "")) != "learned":
        raise ValueError(
            f"train_meta.py expects meta=learned; got meta={cfg.meta.get('name', '?')}"
        )
    meta_cfg = cfg.meta
    train_cfg = meta_cfg.training

    env = _make_env(cfg)

    llm_inner = _instantiate(cfg.llm)
    llm_client = CachedLLMClient(llm_inner, prompt_version=PROMPT_VERSION)

    action_ckpt = cfg.get("action_policy_ckpt", None)
    action_policy = _make_action_policy(cfg, action_ckpt)

    meta_policy: LearnedMetaPolicy = _instantiate(meta_cfg, obs_dim=int(cfg.env.obs_dim))

    trainer = GRPOTrainer(
        meta_policy=meta_policy,
        learning_rate=float(train_cfg.learning_rate),
        call_cost=float(train_cfg.call_cost),
        kl_coef=float(train_cfg.kl_coef),
        group_size=int(train_cfg.group_size),
    )

    wandb_run = None
    wandb_mode = str(cfg.logging.wandb_mode)
    if wandb_mode != "disabled":
        try:
            import wandb

            wandb_run = wandb.init(
                project=cfg.logging.wandb_project,
                mode=wandb_mode,
                config=OmegaConf.to_container(cfg, resolve=True),
                dir=str(run_dir),
                reinit=True,
            )
        except Exception as exc:  # pragma: no cover - non-fatal
            _log.warning("W&B init failed (%s); continuing without it.", exc)
            wandb_run = None

    logger = RolloutLogger(run_dir, use_wandb=wandb_run is not None, wandb_run=wandb_run)

    # `experiment.total_steps` here means total env steps spent training the
    # meta-policy. Each group consumes `group_size * horizon` env steps in
    # the worst case; we convert to a group budget.
    horizon = int(cfg.env.horizon)
    group_size = int(train_cfg.group_size)
    target_total_steps = int(cfg.experiment.total_steps)
    total_groups_cfg = int(train_cfg.get("total_groups", 0))
    if total_groups_cfg > 0:
        budget_groups = total_groups_cfg
    else:
        budget_groups = max(1, target_total_steps // max(1, group_size * horizon))

    print(
        f"[train_meta] starting GRPO: budget_groups={budget_groups} "
        f"group_size={group_size} horizon={horizon}"
    )

    total_env_steps = 0
    for g_idx in range(budget_groups):
        group = [
            collect_meta_rollout(
                env=env,
                action_policy=action_policy,
                meta_policy=meta_policy,
                llm_client=llm_client,
                max_steps=horizon,
                seed=int(cfg.experiment.seed) + g_idx,
            )
            for _ in range(group_size)
        ]
        total_env_steps += sum(len(r.decisions) for r in group)

        metrics = trainer.update(group)

        for k, v in metrics.items():
            logger.log_scalar(f"grpo/{k}", float(v), step=total_env_steps)

        mean_calls = metrics["mean_calls"]
        mean_R = metrics["mean_R"]
        _log.info(
            "group=%d total_steps=%d policy_loss=%.4f kl=%.4f mean_R=%.4f mean_calls=%.2f",
            g_idx,
            total_env_steps,
            metrics["policy_loss"],
            metrics["kl"],
            mean_R,
            mean_calls,
        )

        if (g_idx + 1) % _REF_REFRESH_INTERVAL == 0:
            trainer.update_reference()

        if total_env_steps >= target_total_steps:
            break

    # Final checkpoint.
    ckpt_path = run_dir / "meta_policy.pt"
    torch.save(meta_policy.state_dict(), ckpt_path)
    print(f"[train_meta] saved checkpoint: {ckpt_path}")

    paths = logger.flush()
    _log.info("Wrote logs: %s", {k: str(v) for k, v in paths.items()})

    if wandb_run is not None:
        wandb_run.finish()

    env.close()


if __name__ == "__main__":
    main()
