"""Smoke tests for :mod:`src.envs.unity_env`.

We can't actually instantiate :class:`UnityOvercookedEnv` here because that
requires either a Unity build or a running Unity Editor. These tests only
verify the import path and the missing-dependency error path, which catches
the most common breakage (a typo in the module path or in the lazy-import
logic).
"""

from __future__ import annotations


def test_unity_env_class_importable() -> None:
    from src.envs.unity_env import UnityOvercookedEnv

    assert UnityOvercookedEnv is not None


def test_unity_env_inherits_overcooked_env() -> None:
    from src.envs.base import OvercookedEnv
    from src.envs.unity_env import UnityOvercookedEnv

    assert issubclass(UnityOvercookedEnv, OvercookedEnv)


def test_unity_env_init_without_mlagents_raises() -> None:
    """Without ``mlagents-envs`` installed, instantiation raises ``RuntimeError``."""

    try:
        import mlagents_envs  # noqa: F401
    except ImportError:
        pass
    else:
        import pytest

        pytest.skip(
            "mlagents-envs is installed; cannot test missing-dep error path"
        )

    import pytest

    from src.envs.unity_env import UnityOvercookedEnv

    with pytest.raises(RuntimeError, match="mlagents"):
        UnityOvercookedEnv(build_path="/nonexistent")
