"""End-to-end checkpoint round-trip tests.

These spawn ``scripts/train.py`` as a subprocess against the dummy env so
the harness exercise mirrors how a researcher would actually use it. The
runs are tiny (a single rollout iteration) to keep wallclock under a
couple of seconds.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _run_short_train(tmp_path: Path) -> Path:
    """Run train.py for one rollout iteration; return the run dir."""
    log_dir = tmp_path / "runs"
    log_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "scripts/train.py",
        "env=dummy",
        "meta=fixed_k100",
        "policy=ppo",
        "experiment.total_steps=64",
        "experiment.rollout_steps=64",
        f"experiment.log_dir={log_dir}",
        "logging.wandb_mode=disabled",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"train.py failed (rc={result.returncode}):\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )

    # Hydra creates exactly one run directory under log_dir.
    candidates = [p for p in log_dir.iterdir() if p.is_dir()]
    assert len(candidates) == 1, f"Expected one run dir, got {candidates}"
    return candidates[0]


def test_train_saves_checkpoint(tmp_path: Path) -> None:
    """train.py must drop ``policy.pt`` and an eval results parquet."""
    run_dir = _run_short_train(tmp_path)
    ckpt = run_dir / "policy.pt"
    assert ckpt.exists(), f"missing checkpoint at {ckpt}"
    eval_path = run_dir / "eval_results.parquet"
    assert eval_path.exists(), f"missing eval results at {eval_path}"

    # Load it back the same way eval.py does.
    import torch

    payload = torch.load(ckpt, map_location="cpu", weights_only=False)
    assert isinstance(payload, dict)
    assert "policy_state_dict" in payload
    assert "config" in payload
    assert payload["obs_dim"] > 0
    assert payload["action_dim"] > 0


def test_eval_loads_checkpoint(tmp_path: Path) -> None:
    """After training, scripts/eval.py reads the checkpoint without error."""
    run_dir = _run_short_train(tmp_path)
    assert (run_dir / "policy.pt").exists()

    cmd = [
        sys.executable,
        "scripts/eval.py",
        f"+run_dir={run_dir}",
        "+n_episodes=2",
        "logging.wandb_mode=disabled",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"eval.py failed (rc={result.returncode}):\n"
            f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
        )

    # eval.py overwrites eval_results.parquet and writes eval_summary.json.
    assert (run_dir / "eval_results.parquet").exists()
    assert (run_dir / "eval_summary.json").exists()


def test_checkpoint_load_state_dict_is_compatible(tmp_path: Path) -> None:
    """Re-instantiating the policy and loading the checkpoint round-trips.

    This isolates the load path from eval.py so a regression in the
    checkpoint format is caught even if subprocess paths break.
    """
    run_dir = _run_short_train(tmp_path)

    import torch

    from src.policies import PPOPolicy

    payload = torch.load(run_dir / "policy.pt", map_location="cpu", weights_only=False)
    policy = PPOPolicy(
        obs_dim=int(payload["obs_dim"]),
        action_dim=int(payload["action_dim"]),
        hidden_dim=128,
        n_layers=2,
    )
    missing, unexpected = policy.load_state_dict(
        payload["policy_state_dict"], strict=False
    )
    # The freshly-built policy mirrors the trainer's architecture, so no
    # missing or unexpected keys should be present.
    assert not list(missing)
    assert not list(unexpected)

    # Cleanup: don't leave an arbitrarily-named run dir behind in tmp.
    shutil.rmtree(run_dir, ignore_errors=True)
