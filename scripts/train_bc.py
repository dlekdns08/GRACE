"""Train a PPO actor-critic on human demos via behaviour cloning (Phase 9).

The resulting checkpoint is intended to be loaded by ``scripts/train.py``
as a warm-start for PPO (Phase 11). The checkpoint format is the same
state_dict format PPO uses, so the load path is just
``policy.load_state_dict(torch.load(ckpt))``.

Example:

  .venv/bin/python scripts/train_bc.py \\
      --demos demos/coop_session.parquet \\
      --env-config dummy \\
      --out runs/bc_init.pt \\
      --epochs 20 --batch-size 256 --lr 1e-3
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Allow `python scripts/train_bc.py` from repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import torch  # noqa: E402

from src.policies import LLMAugmentedPPOPolicy, PPOPolicy  # noqa: E402
from src.training.bc import BCDataset, load_demos_to_dataset, train_bc  # noqa: E402

_log = logging.getLogger("train_bc")


# Hard-coded env defaults used when ``--env-config`` is not pointing at a
# Hydra config file. Mirrors ``configs/env/*.yaml`` but does not depend on
# Hydra so this script stays light.
_ENV_DEFAULTS: dict[str, dict[str, int]] = {
    "dummy": {"obs_dim": 8, "action_dim": 6},
    "cramped_room": {"obs_dim": 96, "action_dim": 6},
    "asymmetric_advantages": {"obs_dim": 96, "action_dim": 6},
}


def _resolve_env_config(env_config: str) -> dict[str, int]:
    """Pick env (obs_dim, action_dim) either from a YAML file or a known name."""
    if env_config in _ENV_DEFAULTS:
        return dict(_ENV_DEFAULTS[env_config])
    path = Path(env_config)
    if path.exists():
        try:
            import yaml

            with path.open() as f:
                doc = yaml.safe_load(f) or {}
            return {
                "obs_dim": int(doc.get("obs_dim", 0)),
                "action_dim": int(doc.get("action_dim", 0)),
            }
        except Exception as exc:
            raise RuntimeError(f"Failed to read env config {path}: {exc}") from exc
    raise ValueError(
        f"--env-config must be one of {sorted(_ENV_DEFAULTS)} or a path to a YAML file"
    )


def _build_policy(args: argparse.Namespace, obs_dim: int, action_dim: int) -> PPOPolicy:
    common = {
        "obs_dim": int(obs_dim),
        "action_dim": int(action_dim),
        "hidden_dim": int(args.hidden_dim),
        "n_layers": int(args.n_layers),
        "device": str(args.device),
    }
    if args.policy == "llm_augmented":
        return LLMAugmentedPPOPolicy(**common)
    return PPOPolicy(**common)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="train_bc")
    parser.add_argument("--demos", required=True, help="Parquet of human demonstrations")
    parser.add_argument(
        "--env-config",
        dest="env_config",
        default="dummy",
        help="Env name (dummy/cramped_room/...) or path to a YAML",
    )
    parser.add_argument("--out", required=True, help="Output checkpoint path (.pt)")
    parser.add_argument("--policy", default="ppo", choices=["ppo", "llm_augmented"])
    parser.add_argument("--hidden-dim", dest="hidden_dim", type=int, default=128)
    parser.add_argument("--n-layers", dest="n_layers", type=int, default=2)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", dest="batch_size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", dest="weight_decay", type=float, default=0.0)
    parser.add_argument("--device", default="cpu")
    parser.add_argument(
        "--agent-ids",
        dest="agent_ids",
        default=None,
        help="Comma-separated whitelist of agent ids; default = use all",
    )
    parser.add_argument("--log-level", default="INFO")

    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    env_dims = _resolve_env_config(args.env_config)
    if env_dims["obs_dim"] <= 0 or env_dims["action_dim"] <= 0:
        raise ValueError(f"Resolved env dims invalid: {env_dims}")

    agent_ids: list[str] | None = None
    if args.agent_ids:
        agent_ids = [a.strip() for a in args.agent_ids.split(",") if a.strip()]

    dataset: BCDataset = load_demos_to_dataset(args.demos, agent_ids=agent_ids)
    _log.info(
        "loaded demo dataset: N=%d  obs_dim=%d  expected obs_dim=%d",
        len(dataset),
        dataset.obs_dim,
        env_dims["obs_dim"],
    )
    if dataset.obs_dim != env_dims["obs_dim"]:
        raise ValueError(
            f"Demo obs_dim {dataset.obs_dim} != env obs_dim {env_dims['obs_dim']}; "
            "are you loading a dummy demo with --env-config cramped_room?"
        )

    policy = _build_policy(args, env_dims["obs_dim"], env_dims["action_dim"])
    metrics = train_bc(
        policy=policy,
        dataset=dataset,
        n_epochs=int(args.epochs),
        batch_size=int(args.batch_size),
        learning_rate=float(args.lr),
        weight_decay=float(args.weight_decay),
        device=str(args.device),
        log_every=max(1, int(args.epochs) // 5),
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "state_dict": policy.state_dict(),
        "metrics": metrics,
        "policy": args.policy,
        "obs_dim": env_dims["obs_dim"],
        "action_dim": env_dims["action_dim"],
        "hidden_dim": args.hidden_dim,
        "n_layers": args.n_layers,
        "source": "behaviour_cloning",
    }
    torch.save(payload, out_path)
    _log.info("wrote BC checkpoint to %s; metrics=%s", out_path, json.dumps(metrics))


if __name__ == "__main__":  # pragma: no cover - manual entry point
    main()
