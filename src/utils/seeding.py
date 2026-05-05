"""Deterministic seeding helpers."""

from __future__ import annotations

import os
import random

import numpy as np


def seed_everything(seed: int) -> None:
    """Seed Python, numpy, and torch (if available) for reproducibility."""
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import torch

        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            torch.mps.manual_seed(seed)
    except ImportError:
        pass


def derive_seed(base: int, *salts: int | str) -> int:
    """Derive a stable child seed from a base seed plus arbitrary salts."""
    h = hash((base, *salts)) & 0x7FFFFFFF
    return h
