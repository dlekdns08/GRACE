"""Deterministic state -> text serialisation (DESIGN section 4.2).

Two input shapes are supported:

* :class:`GenericState` -- a plain dataclass used by tests and the in-memory
  DummyOvercookedEnv. Has no external dependencies.
* Carroll's ``OvercookedState`` -- only used when ``overcooked_ai_py`` is
  importable. Otherwise the corresponding branch raises ``NotImplementedError``.

The output format is identical for both branches so caches and prompt templates
stay stable across simulators. Bumping the format requires bumping
:data:`STATE_TEXT_VERSION` so prompt-hash caches invalidate automatically.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    pass


STATE_TEXT_VERSION = "v1"


@dataclass
class GenericPlayer:
    """Test/dummy-env representation of an agent."""

    name: str
    position: tuple[int, int]
    held_item: str | None  # None | "onion" | "dish" | "soup"


@dataclass
class GenericPot:
    """Test/dummy-env representation of a pot.

    ``cooking_time_left`` of 0 with ``onion_count < 3`` means "not started".
    ``is_ready`` indicates a finished soup ready to be plated.
    """

    onion_count: int
    cooking_time_left: int
    is_ready: bool


@dataclass
class GenericState:
    timestep: int
    max_steps: int
    score: int
    soups_served: int
    players: list[GenericPlayer]
    pots: list[GenericPot]


def _format_pot_line(idx: int, pot: GenericPot) -> str:
    if pot.is_ready:
        return f"  - Pot {idx}: ready to serve"
    if pot.cooking_time_left > 0:
        return f"  - Pot {idx}: cooking, {pot.cooking_time_left}s remaining"
    if pot.onion_count == 0:
        return f"  - Pot {idx}: empty"
    return f"  - Pot {idx}: {pot.onion_count}/3 onions, not started"


def _generic_state_to_text(state: GenericState) -> str:
    lines: list[str] = [
        f"Step: {state.timestep}/{state.max_steps}",
        f"Score: {state.score} (soups served: {state.soups_served})",
        "",
        "Agents:",
    ]
    # Sort agents alphabetically by name for determinism.
    for player in sorted(state.players, key=lambda p: p.name):
        held = player.held_item if player.held_item is not None else "nothing"
        x, y = player.position
        lines.append(f"  - {player.name} at ({x},{y}), holding {held}")

    lines.append("")
    lines.append("Pots:")
    # Pots are sorted by index (preserve order; index = position in list).
    for idx, pot in enumerate(state.pots):
        lines.append(_format_pot_line(idx, pot))

    return "\n".join(lines)


def _overcooked_state_to_text(state: Any) -> str:
    """Convert Carroll's ``OvercookedState`` to the same format.

    Only invoked when ``overcooked_ai_py`` is importable; otherwise the caller
    short-circuits to :class:`GenericState`.
    """
    try:
        import overcooked_ai_py  # noqa: F401
    except ImportError as e:  # pragma: no cover - defensive
        raise NotImplementedError("overcooked_ai_py not installed") from e

    # The full Carroll-state branch will be filled in once Phase 6 wires the
    # python_env to the Overcooked-AI fixtures. The format below mirrors the
    # generic branch exactly so callers cannot tell them apart.
    raise NotImplementedError(
        "overcooked_ai_py state -> text conversion is not yet wired in; "
        "pass a GenericState for now."
    )


def state_to_text(state: Any) -> str:
    """Convert a state to its deterministic text representation.

    Accepts :class:`GenericState` directly. Anything else is treated as a
    Carroll ``OvercookedState`` and routed through the (currently stubbed)
    overcooked-ai path.
    """
    if isinstance(state, GenericState):
        return _generic_state_to_text(state)
    return _overcooked_state_to_text(state)
