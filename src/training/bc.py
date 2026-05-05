"""Behaviour cloning for warm-starting PPO from human demonstrations (Phase 9).

Pipeline:

  1. ``scripts/play_human.py`` records per-step rows
     ``(episode, step, agent_id, raw_obs, action, reward, done, source)``
     to a parquet file.
  2. :func:`load_demos_to_dataset` reads that parquet and returns a single
     :class:`BCDataset` flattened across episodes and agents.
  3. :func:`train_bc` runs supervised cross-entropy on
     ``(obs -> action)`` pairs against any policy that exposes
     ``forward(obs) -> (logits, value)``. The same checkpoint format used
     by PPO is therefore drop-in: Phase 11 (PPO trainer) can load the
     resulting state_dict via a ``+init_checkpoint=...`` override.

The dataset format is intentionally minimal — just the supervised pair
plus enough metadata to recover the demo source if we ever want to
filter on `source == "human"` for instance.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F  # noqa: N812
from torch.utils.data import DataLoader, TensorDataset

_log = logging.getLogger(__name__)


REQUIRED_COLUMNS: tuple[str, ...] = (
    "episode",
    "step",
    "agent_id",
    "raw_obs",
    "action",
)


@dataclass(slots=True)
class BCDataset:
    """In-memory supervised dataset of ``(obs, action)`` pairs.

    Both arrays have a leading ``N`` dimension where ``N`` is the total
    number of demo transitions across all episodes and selected agents.
    ``obs`` is float32, ``actions`` is int64. The dataset is fully
    materialised in RAM — demo corpora are small (human playthroughs).
    """

    obs: np.ndarray
    actions: np.ndarray

    def __post_init__(self) -> None:
        if self.obs.ndim != 2:
            raise ValueError(f"obs must be 2D [N, obs_dim]; got shape {self.obs.shape}")
        if self.actions.ndim != 1:
            raise ValueError(f"actions must be 1D [N]; got shape {self.actions.shape}")
        if self.obs.shape[0] != self.actions.shape[0]:
            raise ValueError(
                f"obs/actions length mismatch: {self.obs.shape[0]} vs {self.actions.shape[0]}"
            )
        if self.obs.dtype != np.float32:
            self.obs = self.obs.astype(np.float32, copy=False)
        if self.actions.dtype != np.int64:
            self.actions = self.actions.astype(np.int64, copy=False)

    def __len__(self) -> int:
        return int(self.obs.shape[0])

    @property
    def obs_dim(self) -> int:
        return int(self.obs.shape[1])


# --------------------------------------------------------------------------- loader
def _coerce_obs(value: Any) -> np.ndarray:
    """Convert one parquet ``raw_obs`` cell into a 1-D float32 array.

    pandas+pyarrow turns Python lists into ``numpy.ndarray`` of dtype
    ``object`` or ``float64``; we normalise both to float32. Bytes are
    rejected explicitly because they would silently load as length-N byte
    arrays (a confusing failure mode).
    """
    if isinstance(value, (bytes, bytearray)):
        raise TypeError("raw_obs must be a list/array of floats, not bytes")
    arr = np.asarray(value, dtype=np.float32).reshape(-1)
    return arr


def load_demos_to_dataset(
    parquet_path: str | Path,
    agent_ids: list[str] | None = None,
) -> BCDataset:
    """Load a human-demo parquet and flatten it into one :class:`BCDataset`.

    Args:
        parquet_path: Path to a parquet file produced by
            ``scripts/play_human.py`` (or a compatible recorder). Must
            include columns ``REQUIRED_COLUMNS``.
        agent_ids: Optional whitelist. When ``None`` all agents are kept.

    Returns:
        A :class:`BCDataset` with rows in the file's natural order
        (episode, step, agent). Rows whose ``raw_obs`` is empty / null are
        silently skipped — a few zero-length rows can sneak in if a
        recording was interrupted between an env step and the row write.
    """
    path = Path(parquet_path)
    if not path.exists():
        raise FileNotFoundError(f"Demo parquet not found: {path}")
    df = pd.read_parquet(path)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Demo parquet missing required columns: {missing}")

    if agent_ids is not None:
        df = df[df["agent_id"].isin(list(agent_ids))]
    if df.empty:
        raise ValueError(f"No demo rows after filtering (agent_ids={agent_ids})")

    obs_list: list[np.ndarray] = []
    actions_list: list[int] = []
    skipped = 0
    obs_dim: int | None = None
    for raw_obs, action in zip(df["raw_obs"].tolist(), df["action"].tolist(), strict=True):
        try:
            arr = _coerce_obs(raw_obs)
        except Exception:
            skipped += 1
            continue
        if arr.size == 0:
            skipped += 1
            continue
        if obs_dim is None:
            obs_dim = int(arr.shape[0])
        elif arr.shape[0] != obs_dim:
            skipped += 1
            continue
        obs_list.append(arr)
        actions_list.append(int(action))

    if not obs_list:
        raise ValueError(f"No usable demo rows in {path} (skipped={skipped})")

    obs = np.stack(obs_list, axis=0).astype(np.float32, copy=False)
    actions = np.asarray(actions_list, dtype=np.int64)
    if skipped:
        _log.info("load_demos_to_dataset: skipped %d malformed rows", skipped)
    return BCDataset(obs=obs, actions=actions)


# --------------------------------------------------------------------------- trainer
def _policy_logits(policy: nn.Module, obs_batch: torch.Tensor) -> torch.Tensor:
    """Call ``policy.forward`` and unpack logits whether or not it returns a value head.

    PPOPolicy returns ``(logits, value)``; a generic ``nn.Module`` may
    return logits directly. We support both shapes so the trainer is
    reusable for non-PPO baselines too.
    """
    out = policy.forward(obs_batch)
    if isinstance(out, tuple):
        return out[0]
    return out


def train_bc(
    policy: nn.Module,
    dataset: BCDataset,
    n_epochs: int = 10,
    batch_size: int = 256,
    learning_rate: float = 1e-3,
    device: str = "cpu",
    weight_decay: float = 0.0,
    shuffle: bool = True,
    log_every: int = 0,
) -> dict[str, float]:
    """Train ``policy`` by cross-entropy against ``(obs, action)`` pairs.

    Updates ``policy`` in place. The optimiser is plain Adam — BC is
    typically convex enough that hyperparameter tuning brings little
    return; if PPO fine-tuning later struggles, the right move is more
    demos rather than a fancier BC schedule.

    Returns the final-epoch loss, accuracy, and the number of optimisation
    steps taken. Convenient for logging and for asserting in tests that
    the optimisation actually did something.
    """
    if n_epochs <= 0:
        raise ValueError("n_epochs must be positive")
    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    if len(dataset) == 0:
        raise ValueError("dataset is empty")

    dev = torch.device(device)
    policy.to(dev)
    policy.train()

    obs_t = torch.as_tensor(dataset.obs, dtype=torch.float32)
    act_t = torch.as_tensor(dataset.actions, dtype=torch.long)
    tensor_ds = TensorDataset(obs_t, act_t)
    loader = DataLoader(tensor_ds, batch_size=batch_size, shuffle=shuffle)

    optimizer = torch.optim.Adam(
        policy.parameters(), lr=float(learning_rate), weight_decay=float(weight_decay)
    )

    last_loss = float("nan")
    last_acc = float("nan")
    n_updates = 0
    for epoch in range(int(n_epochs)):
        epoch_loss_sum = 0.0
        epoch_correct = 0
        epoch_total = 0
        for obs_batch, act_batch in loader:
            obs_batch = obs_batch.to(dev)
            act_batch = act_batch.to(dev)

            logits = _policy_logits(policy, obs_batch)
            loss = F.cross_entropy(logits, act_batch)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            n_updates += 1

            epoch_loss_sum += float(loss.item()) * obs_batch.shape[0]
            preds = logits.argmax(dim=-1)
            epoch_correct += int((preds == act_batch).sum().item())
            epoch_total += int(obs_batch.shape[0])

        last_loss = epoch_loss_sum / max(epoch_total, 1)
        last_acc = epoch_correct / max(epoch_total, 1)
        if log_every and (epoch + 1) % int(log_every) == 0:
            _log.info(
                "BC epoch %d/%d  loss=%.4f  acc=%.3f", epoch + 1, n_epochs, last_loss, last_acc
            )

    policy.eval()
    return {
        "final_loss": float(last_loss),
        "final_accuracy": float(last_acc),
        "n_updates": float(n_updates),
        "n_examples": float(len(dataset)),
        "n_epochs": float(n_epochs),
    }


__all__ = [
    "BCDataset",
    "REQUIRED_COLUMNS",
    "load_demos_to_dataset",
    "train_bc",
]
