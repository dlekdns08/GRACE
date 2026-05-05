"""Hydra entry point for zero-shot transfer evaluation (DESIGN H2).

Loads a trained checkpoint from ``+train_run=runs/<dir>/`` (i.e., the
config + ``policy.pt`` produced by :mod:`scripts.train`), builds the
same policy / meta / LLM stack against the *original* config, and then
runs evaluation on each layout listed in ``+test_layouts=[...]``.

Usage::

    python scripts/eval_transfer.py \\
        +train_run=runs/learned_cramped_room_llm_augmented_seed0_<ts>/ \\
        +test_layouts=[asymmetric_advantages] \\
        +n_episodes=10
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Make ``src.*`` importable when this script is invoked directly.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import hydra  # noqa: E402
from omegaconf import DictConfig, OmegaConf  # noqa: E402

from src.eval.transfer import evaluate_transfer  # noqa: E402
from src.llm import PROMPT_VERSION, CachedLLMClient  # noqa: E402
from src.policies import MetaPolicy, PPOPolicy  # noqa: E402

_log = logging.getLogger(__name__)


def _instantiate(cfg_node, **kwargs):
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


def _markdown_table(df) -> str:
    """Render a small DataFrame as a github-flavoured markdown table."""
    if df.empty:
        return "(no transfer rows)"
    cols = list(df.columns)
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
    ]
    for _, row in df.iterrows():
        cells = []
        for c in cols:
            v = row[c]
            if isinstance(v, float):
                cells.append(f"{v:.3f}")
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


@hydra.main(version_base=None, config_path="../configs", config_name="base")
def main(cfg: DictConfig) -> None:
    train_run = cfg.get("train_run", None)
    if train_run is None:
        raise ValueError(
            "scripts/eval_transfer.py requires +train_run=<path>. "
            "Example: python scripts/eval_transfer.py "
            "+train_run=runs/<run> +test_layouts=[asymmetric_advantages]"
        )
    train_dir = Path(str(train_run)).resolve()
    if not train_dir.exists():
        raise FileNotFoundError(f"train_run does not exist: {train_dir}")

    cfg_path = train_dir / "config.yaml"
    if not cfg_path.exists():
        raise FileNotFoundError(f"Missing {cfg_path}; was training ever run here?")
    cfg_run = OmegaConf.load(cfg_path)
    if not isinstance(cfg_run, DictConfig):
        raise TypeError(f"Expected a DictConfig from {cfg_path}")

    raw_test = cfg.get("test_layouts", None)
    if raw_test is None:
        raise ValueError("scripts/eval_transfer.py requires +test_layouts=[...].")
    if isinstance(raw_test, str):
        test_layouts = [raw_test]
    else:
        test_layouts = [str(x) for x in raw_test]

    n_episodes = int(cfg.get("n_episodes", 10))

    train_layout = str(cfg_run.env.get("layout", cfg_run.env.get("name", "unknown")))

    # Defensive: bail out cleanly if overcooked_ai_py isn't installed.
    try:
        from src.envs.python_env import PythonOvercookedEnv  # noqa: F401
    except Exception as exc:
        _log.error("PythonOvercookedEnv unavailable (%s); skipping transfer evaluation.", exc)
        return

    # Build the LLM client (cached) from the original run's config.
    llm_inner = _instantiate(cfg_run.llm)
    llm_client = CachedLLMClient(llm_inner, prompt_version=PROMPT_VERSION)

    # Policy ctor: re-instantiate per layout so each eval starts from the
    # same checkpoint state.
    obs_dim = int(cfg_run.env.obs_dim)
    action_dim = int(cfg_run.env.action_dim)
    policy_cfg = cfg_run.policy

    def policy_ctor() -> PPOPolicy:
        return _instantiate(policy_cfg, obs_dim=obs_dim, action_dim=action_dim)

    # Meta-policy: instantiate once and reuse (deterministic in eval mode).
    try:
        meta_policy: MetaPolicy = _instantiate(cfg_run.meta)
    except TypeError:
        meta_policy = _instantiate(cfg_run.meta, policy=policy_ctor())
    if hasattr(meta_policy, "attach"):
        # Late-binding hooks expect a policy reference; make a fresh one
        # so the meta-policy isn't tied to a particular eval policy.
        meta_policy.attach(policy_ctor())

    ckpt_path = train_dir / "policy.pt"
    if not ckpt_path.exists():
        _log.warning(
            "No policy.pt at %s; transfer eval will use freshly initialised weights.",
            ckpt_path,
        )

    df = evaluate_transfer(
        train_layout=train_layout,
        test_layouts=test_layouts,
        policy_ctor=policy_ctor,
        checkpoint_path=ckpt_path,
        meta_policy=meta_policy,
        llm_client=llm_client,
        n_episodes=n_episodes,
    )

    out_path = train_dir / "transfer_results.parquet"
    df.to_parquet(out_path, index=False)
    _log.info("Wrote %s (%d rows)", out_path, len(df))

    # Print a human-readable summary that the shell scripts can capture.
    print(f"\n# Transfer results for {train_dir.name}\n")
    print(_markdown_table(df))
    print()


if __name__ == "__main__":
    main()
