"""Hydra entry point for PPO + meta-policy training (DESIGN section 5).

Composes env / policy / meta / llm via Hydra config groups and drives
the standard rollout-then-update loop until ``experiment.total_steps`` is
reached. Logs go to a per-run directory; W&B is optional.
"""

from __future__ import annotations

import logging
from pathlib import Path

import hydra
import torch
from hydra.core.hydra_config import HydraConfig
from omegaconf import DictConfig, OmegaConf

from src.envs import DummyOvercookedEnv, OvercookedEnv
from src.eval.metrics import aggregate_episodes
from src.eval.runner import run_eval
from src.llm import PROMPT_VERSION, CachedLLMClient
from src.policies import MetaPolicy, PPOPolicy
from src.training import PPOTrainer, collect_rollout
from src.utils import RolloutLogger, save_resolved_config, seed_everything


_log = logging.getLogger(__name__)


def _instantiate(cfg_node: DictConfig, **kwargs):
    """Instantiate via `_target_`, dropping convention-only keys like `name`.

    Configs include human-readable `name` fields (used in run-dir formatting
    and W&B grouping) that aren't constructor arguments. Strip them before
    delegating to `hydra.utils.instantiate`.
    """
    plain = OmegaConf.to_container(cfg_node, resolve=True)
    if not isinstance(plain, dict):
        raise TypeError(f"Expected dict-like config; got {type(plain).__name__}")
    plain = {k: v for k, v in plain.items() if k != "name"}
    plain.update(kwargs)
    return hydra.utils.instantiate(plain)


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
    """Return the Hydra-managed run directory."""
    try:
        hc = HydraConfig.get()
        return Path(hc.runtime.output_dir)
    except Exception:
        return Path.cwd()


@hydra.main(version_base=None, config_path="../configs", config_name="base")
def main(cfg: DictConfig) -> None:
    seed_everything(int(cfg.experiment.seed))
    run_dir = _resolve_run_dir(cfg)
    run_dir.mkdir(parents=True, exist_ok=True)
    save_resolved_config(cfg, run_dir / "config.yaml")

    env = _make_env(cfg)

    # LLM: instantiate via _target_, wrap in cache.
    llm_inner = _instantiate(cfg.llm)
    llm_client = CachedLLMClient(llm_inner, prompt_version=PROMPT_VERSION)

    # Action policy: pass obs_dim/action_dim from the env config.
    policy: PPOPolicy = _instantiate(
        cfg.policy,
        obs_dim=int(cfg.env.obs_dim),
        action_dim=int(cfg.env.action_dim),
    )

    # Meta-policy: some variants need a reference to the action policy
    # (e.g. EntropyMetaPolicy looks at the policy's own logits).
    try:
        meta_policy: MetaPolicy = _instantiate(cfg.meta)
    except TypeError:
        meta_policy = _instantiate(cfg.meta, policy=policy)

    # If the meta-policy supports late-binding to the action policy
    # (e.g. EntropyMetaPolicy.attach), wire it up here so it can read
    # the policy's logits at decision time.
    if hasattr(meta_policy, "attach"):
        meta_policy.attach(policy)

    # Optional W&B.
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
    trainer = PPOTrainer(policy, cfg.policy)

    total_steps = 0
    iteration = 0
    target_steps = int(cfg.experiment.total_steps)
    rollout_steps = int(cfg.experiment.rollout_steps)
    eval_every = int(cfg.experiment.get("eval_every", 0) or 0)
    last_ckpt_step = 0

    def _save_checkpoint(path: Path) -> None:
        torch.save(
            {
                "policy_state_dict": policy.state_dict(),
                "policy_class": policy.__class__.__name__,
                "obs_dim": int(cfg.env.obs_dim),
                "action_dim": int(cfg.env.action_dim),
                "use_subgoal": bool(getattr(policy, "use_subgoal", False)),
                "subgoal_dim": int(getattr(policy, "subgoal_dim", 0)),
                "config": OmegaConf.to_container(cfg, resolve=True),
            },
            path,
        )

    while total_steps < target_steps:
        batch = collect_rollout(
            env=env,
            policy=policy,
            meta_policy=meta_policy,
            llm_client=llm_client,
            n_steps=rollout_steps,
            logger=logger,
            episode_id=iteration,
        )
        metrics = trainer.update(batch)
        total_steps += rollout_steps
        iteration += 1

        for k, v in metrics.items():
            logger.log_scalar(f"train/{k}", float(v), step=total_steps)

        if batch.episode_returns:
            mean_return = float(sum(batch.episode_returns) / len(batch.episode_returns))
            mean_length = float(sum(batch.episode_lengths) / len(batch.episode_lengths))
            mean_soup = float(sum(batch.soup_counts) / len(batch.soup_counts))
            logger.log_scalar("rollout/mean_return", mean_return, step=total_steps)
            logger.log_scalar("rollout/mean_length", mean_length, step=total_steps)
            logger.log_scalar("rollout/mean_soup_count", mean_soup, step=total_steps)
        logger.log_scalar("rollout/llm_calls", float(batch.n_llm_calls), step=total_steps)
        logger.log_scalar(
            "rollout/cached_calls", float(batch.n_cached_calls), step=total_steps
        )

        _log.info(
            "iter=%d total_steps=%d episodes=%d llm_calls=%d policy_loss=%.4f",
            iteration,
            total_steps,
            len(batch.episode_returns),
            batch.n_llm_calls,
            metrics["policy_loss"],
        )

    paths = logger.flush()
    _log.info("Wrote logs: %s", {k: str(v) for k, v in paths.items()})

    if wandb_run is not None:
        wandb_run.finish()

    env.close()


if __name__ == "__main__":
    main()
