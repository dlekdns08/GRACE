"""Hydra entry point for evaluation (DESIGN section 7).

Loads the resolved config from a previous training run, rebuilds the
env / policy / meta / llm via the same ``_target_`` instantiation pattern
as :mod:`scripts.train`, and writes per-episode results to
``eval_results.parquet`` plus aggregated stats to ``eval_summary.json``
inside the run directory.

Usage:

    python scripts/eval.py +run_dir=runs/<run> n_episodes=10
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

# Make ``src.*`` importable when this script is invoked directly.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import hydra  # noqa: E402
from omegaconf import DictConfig, OmegaConf  # noqa: E402

from src.envs import DummyOvercookedEnv, OvercookedEnv  # noqa: E402
from src.eval import aggregate_episodes, run_eval  # noqa: E402
from src.llm import PROMPT_VERSION, CachedLLMClient  # noqa: E402
from src.policies import MetaPolicy, PPOPolicy  # noqa: E402

_log = logging.getLogger(__name__)


def _instantiate(cfg_node: DictConfig | dict, **kwargs):
    """Mirror of scripts.train._instantiate — strips ``name`` before instantiation."""
    if isinstance(cfg_node, DictConfig):
        plain = OmegaConf.to_container(cfg_node, resolve=True)
    else:
        plain = dict(cfg_node)
    if not isinstance(plain, dict):
        raise TypeError(f"Expected dict-like config; got {type(plain).__name__}")
    plain = {k: v for k, v in plain.items() if k != "name"}
    plain.update(kwargs)
    return hydra.utils.instantiate(plain)


def _make_env(env_cfg: DictConfig | dict) -> OvercookedEnv:
    """Construct an env from the env-section of a saved config."""
    backend = env_cfg.get("backend") if isinstance(env_cfg, dict) else env_cfg.backend
    horizon = int(env_cfg.get("horizon", 50) if isinstance(env_cfg, dict) else env_cfg.horizon)
    if backend == "dummy":
        return DummyOvercookedEnv(max_steps=horizon)
    if backend == "python":
        from src.envs.python_env import PythonOvercookedEnv

        layout = env_cfg["layout"] if isinstance(env_cfg, dict) else env_cfg.layout
        return PythonOvercookedEnv(layout=layout, horizon=horizon)
    if backend == "unity":
        from src.envs.unity_env import UnityOvercookedEnv  # type: ignore[import-not-found]

        unity_kwargs = (
            env_cfg.get("unity", {}) if isinstance(env_cfg, dict) else (env_cfg.get("unity") or {})
        )
        return UnityOvercookedEnv(**unity_kwargs)
    raise ValueError(f"Unknown env.backend: {backend!r}")


@hydra.main(version_base=None, config_path="../configs", config_name="base")
def main(cfg: DictConfig) -> None:
    # ``+run_dir=...`` is the only required override.
    run_dir_str = cfg.get("run_dir", None)
    if run_dir_str is None:
        raise ValueError(
            "scripts/eval.py requires +run_dir=<path>. "
            "Example: python scripts/eval.py +run_dir=runs/<some_run>"
        )
    run_dir = Path(run_dir_str)
    if not run_dir.exists():
        raise FileNotFoundError(f"run_dir does not exist: {run_dir}")

    cfg_path = run_dir / "config.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError(f"Missing {cfg_path}; was training ever run here?")

    cfg_run = OmegaConf.load(cfg_path)
    if not isinstance(cfg_run, DictConfig):
        raise TypeError(f"Expected a DictConfig from {cfg_path}")

    n_episodes = int(cfg.get("n_episodes", 10))
    seed_base = int(cfg.get("seed_base", 1000))
    max_steps = int(cfg_run.env.get("horizon", 50))

    env = _make_env(cfg_run.env)

    llm_inner = _instantiate(cfg_run.llm)
    llm_client = CachedLLMClient(llm_inner, prompt_version=PROMPT_VERSION)

    policy: PPOPolicy = _instantiate(
        cfg_run.policy,
        obs_dim=int(cfg_run.env.obs_dim),
        action_dim=int(cfg_run.env.action_dim),
    )

    # Optional checkpoint restore — eval still produces valid output without one.
    ckpt_path = run_dir / "policy.pt"
    if ckpt_path.exists():
        try:
            import torch

            # `weights_only=True` is preferred but fails on dict checkpoints
            # that include the resolved Hydra config (non-tensor data).
            try:
                state = torch.load(ckpt_path, map_location="cpu", weights_only=False)
            except TypeError:  # pragma: no cover - older torch
                state = torch.load(ckpt_path, map_location="cpu")
            # Accept either a bare state_dict or our metadata-wrapped dict.
            if isinstance(state, dict) and "policy_state_dict" in state:
                state_dict = state["policy_state_dict"]
            else:
                state_dict = state
            try:
                missing, unexpected = policy.load_state_dict(state_dict, strict=False)
                if missing or unexpected:
                    _log.warning(
                        "load_state_dict mismatch: missing=%s unexpected=%s",
                        list(missing),
                        list(unexpected),
                    )
                _log.info("Loaded policy checkpoint from %s", ckpt_path)
            except Exception as exc:
                _log.warning("load_state_dict raised %s; continuing with fresh weights.", exc)
        except Exception as exc:
            _log.warning("Failed to load %s: %s; continuing with fresh weights.", ckpt_path, exc)
    else:
        _log.info("No policy.pt at %s; evaluating untrained policy.", ckpt_path)

    try:
        meta_policy: MetaPolicy = _instantiate(cfg_run.meta)
    except TypeError:
        meta_policy = _instantiate(cfg_run.meta, policy=policy)
    if hasattr(meta_policy, "attach"):
        meta_policy.attach(policy)

    df = run_eval(
        env=env,
        policy=policy,
        meta_policy=meta_policy,
        llm_client=llm_client,
        n_episodes=n_episodes,
        max_steps_per_episode=max_steps,
        seed_base=seed_base,
    )

    out_parquet = run_dir / "eval_results.parquet"
    df.to_parquet(out_parquet, index=False)
    summary = aggregate_episodes(df)
    out_json = run_dir / "eval_summary.json"
    with open(out_json, "w") as f:
        json.dump(summary, f, indent=2)

    _log.info("Wrote %s and %s", out_parquet, out_json)
    _log.info("Summary: %s", summary)

    env.close()


if __name__ == "__main__":
    main()
