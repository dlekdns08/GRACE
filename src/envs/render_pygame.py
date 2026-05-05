"""Pygame renderer for human-play of Overcooked-style environments (Phase 9).

The renderer is intentionally environment-agnostic: it asks the env (or the
:class:`EnvObservation` it just produced) for a structured snapshot of the
world, and falls back to text parsing when no structured info is available.

Design choices:

* **Lazy ``import pygame``** inside :meth:`PygameRenderer.__init__`. This
  keeps the rest of the package importable in environments where pygame is
  not installed (e.g. CI runners that skip the renderer tests).
* **Headless safe**. Setting ``headless=True`` exports ``SDL_VIDEODRIVER=
  dummy`` *before* pygame is imported. CI tests rely on this so they can
  exercise the draw path with no display attached.
* **Best-effort introspection**. We do not modify other modules to expose
  rendering data. Instead, the renderer tries multiple sources in order:

    1. ``obs.info`` keys (preferred; populated by the Python wrappers).
    2. Direct attribute introspection on the env (``_positions``,
       ``_held``, ``_pot_onions`` etc. on :class:`DummyOvercookedEnv`).
    3. Parsing ``obs.text`` as a last resort.

  None of these are part of the env contract — Phase 9's rendering is
  decoration over the existing API, not a new API.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - typing only
    from src.envs.base import EnvObservation


@dataclass(slots=True)
class _RenderInfo:
    """Structured snapshot used by :meth:`PygameRenderer.draw`.

    All fields are best-effort — missing data simply means the corresponding
    glyph is not drawn.
    """

    grid_width: int
    grid_height: int
    timestep: int
    max_steps: int
    score: float
    soup_count: int
    # Per-agent positions and held items.
    positions: dict[str, tuple[int, int]] = field(default_factory=dict)
    held: dict[str, str | None] = field(default_factory=dict)
    # List of pots: each is (x, y, n_onions, cooking_left, ready).
    pots: list[tuple[int, int, int, int, bool]] = field(default_factory=list)


# --------------------------------------------------------------------------- helpers
_TEXT_PLAYER_RE = re.compile(r"-\s*(\S+)\s*at\s*\(([-0-9]+),\s*([-0-9]+)\),\s*holding\s*(\S+)")
_TEXT_POT_RE = re.compile(
    r"Pot\s+\d+:\s*(empty|cooking,\s*(\d+).*remaining|ready to serve|(\d+)/3 onions)"
)
_TEXT_STEP_RE = re.compile(r"Step:\s*(\d+)/(\d+)")
_TEXT_SCORE_RE = re.compile(r"Score:\s*([-0-9.]+)\s*\(soups served:\s*(\d+)\)")


def _extract_render_info(env: Any, obs: "EnvObservation") -> _RenderInfo:
    """Best-effort extraction of a :class:`_RenderInfo` from env + obs.

    Tries direct attribute access on common dummy/Carroll env shapes first,
    then falls back to parsing the LLM-facing text representation.
    """
    grid_w = int(getattr(env, "_grid_width", 5))
    grid_h = int(getattr(env, "_grid_height", 5))
    # DummyOvercookedEnv uses a square grid hard-coded to 5.
    if not hasattr(env, "_grid_width"):
        grid_w = grid_h = 5

    info = _RenderInfo(
        grid_width=grid_w,
        grid_height=grid_h,
        timestep=int(obs.info.get("timestep", 0)) if obs.info else 0,
        max_steps=0,
        score=0.0,
        soup_count=0,
    )

    # ---- Source 1: env attributes (DummyOvercookedEnv shape) ----
    positions = getattr(env, "_positions", None)
    held = getattr(env, "_held", None)
    if isinstance(positions, dict):
        info.positions = {str(k): tuple(v) for k, v in positions.items() if v is not None}
    if isinstance(held, dict):
        info.held = {str(k): v for k, v in held.items()}

    pot_onions = getattr(env, "_pot_onions", None)
    pot_cook = getattr(env, "_pot_cook_remaining", None)
    pot_ready = getattr(env, "_pot_ready", None)
    pot_pos = (2, 0)  # Default DummyOvercookedEnv pot position.
    try:
        from src.envs.dummy_env import _POT_POSITION as _PP

        pot_pos = _PP
    except Exception:  # pragma: no cover - defensive
        pass
    if pot_onions is not None:
        info.pots = [
            (
                int(pot_pos[0]),
                int(pot_pos[1]),
                int(pot_onions),
                int(pot_cook or 0),
                bool(pot_ready),
            )
        ]

    info.max_steps = int(getattr(env, "_max_steps", info.max_steps))
    info.score = float(getattr(env, "_score", info.score))
    info.soup_count = int(getattr(env, "_soups_served", info.soup_count))

    # ---- Source 2: obs.info structured fields (PythonOvercookedEnv) ----
    obs_info = obs.info or {}
    if "positions" in obs_info and isinstance(obs_info["positions"], dict):
        info.positions = {str(k): tuple(v) for k, v in obs_info["positions"].items()}
    if "held" in obs_info and isinstance(obs_info["held"], dict):
        info.held = {str(k): v for k, v in obs_info["held"].items()}
    if "pots" in obs_info and isinstance(obs_info["pots"], list):
        coerced: list[tuple[int, int, int, int, bool]] = []
        for p in obs_info["pots"]:
            try:
                coerced.append(
                    (int(p[0]), int(p[1]), int(p[2]), int(p[3]), bool(p[4]))
                )
            except Exception:  # pragma: no cover - defensive
                continue
        if coerced:
            info.pots = coerced
    if "grid_width" in obs_info:
        info.grid_width = int(obs_info["grid_width"])
    if "grid_height" in obs_info:
        info.grid_height = int(obs_info["grid_height"])
    if "score" in obs_info:
        info.score = float(obs_info["score"])
    if "soup_count" in obs_info:
        info.soup_count = int(obs_info["soup_count"])
    if "max_steps" in obs_info:
        info.max_steps = int(obs_info["max_steps"])

    # ---- Source 3: parse obs.text as a final fallback ----
    if not info.positions and isinstance(obs.text, str):
        for m in _TEXT_PLAYER_RE.finditer(obs.text):
            name, x, y, holding = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
            info.positions[name] = (x, y)
            info.held[name] = None if holding == "nothing" else holding
        m = _TEXT_STEP_RE.search(obs.text)
        if m:
            info.timestep = int(m.group(1))
            info.max_steps = int(m.group(2))
        m = _TEXT_SCORE_RE.search(obs.text)
        if m:
            info.score = float(m.group(1))
            info.soup_count = int(m.group(2))

    return info


# --------------------------------------------------------------------------- renderer
class PygameRenderer:
    """Pygame renderer for Overcooked-style environments.

    The renderer is constructed once per session and reused across episodes.
    Call :meth:`draw` after every :meth:`OvercookedEnv.reset` /
    :meth:`OvercookedEnv.step` to refresh the display, :meth:`poll_events`
    to drain the OS event queue (required for the window to stay
    responsive even in modes where it is purely a display), and
    :meth:`close` once at exit.
    """

    TILE_SIZE: int = 64
    HUD_HEIGHT: int = 80
    COLORS: dict[str, tuple[int, int, int]] = {
        "empty": (40, 40, 40),
        "counter": (139, 90, 43),
        "pot": (180, 60, 60),
        "pot_cooking": (220, 130, 60),
        "pot_ready": (255, 200, 60),
        "onion_box": (200, 180, 50),
        "dish_box": (220, 220, 220),
        "serve": (50, 200, 50),
        "agent_0": (60, 120, 220),
        "agent_1": (220, 80, 180),
        "onion_held": (255, 230, 100),
        "dish_held": (240, 240, 240),
        "soup_held": (255, 140, 60),
        "hud_bg": (20, 20, 30),
        "hud_text": (240, 240, 240),
        "grid_line": (70, 70, 70),
    }

    def __init__(self, width: int = 5, height: int = 5, headless: bool = False) -> None:
        if headless:
            # SDL must read this before pygame.display is initialised.
            os.environ["SDL_VIDEODRIVER"] = "dummy"

        # Lazy import keeps the package importable when pygame is missing.
        import pygame

        self._pygame = pygame
        self._headless = bool(headless)
        self.grid_width = int(width)
        self.grid_height = int(height)

        pygame.init()
        if not pygame.font.get_init():  # pragma: no cover - defensive
            pygame.font.init()

        self._win_w = self.grid_width * self.TILE_SIZE
        self._win_h = self.grid_height * self.TILE_SIZE + self.HUD_HEIGHT
        flags = 0
        if not headless:
            try:
                pygame.display.set_caption("GRACE Overcooked - human play")
            except pygame.error:  # pragma: no cover - defensive
                pass
        self.surface = pygame.display.set_mode((self._win_w, self._win_h), flags)
        self.font = pygame.font.SysFont("monospace", 16)
        self.big_font = pygame.font.SysFont("monospace", 22, bold=True)

    # ----------------------------------------------------------------- drawing
    def _grid_to_px(self, x: int, y: int) -> tuple[int, int]:
        """Translate grid coords (origin bottom-left) to pixel top-left.

        We flip the Y axis so the user sees a conventional "up = up" layout
        even though the env stores positions with y growing upward.
        """
        flipped_y = (self.grid_height - 1) - int(y)
        return int(x) * self.TILE_SIZE, flipped_y * self.TILE_SIZE

    def _draw_grid(self) -> None:
        pg = self._pygame
        self.surface.fill(self.COLORS["empty"])
        for gx in range(self.grid_width + 1):
            pg.draw.line(
                self.surface,
                self.COLORS["grid_line"],
                (gx * self.TILE_SIZE, 0),
                (gx * self.TILE_SIZE, self.grid_height * self.TILE_SIZE),
                width=1,
            )
        for gy in range(self.grid_height + 1):
            pg.draw.line(
                self.surface,
                self.COLORS["grid_line"],
                (0, gy * self.TILE_SIZE),
                (self.grid_width * self.TILE_SIZE, gy * self.TILE_SIZE),
                width=1,
            )

    def _draw_pot(self, pot: tuple[int, int, int, int, bool]) -> None:
        pg = self._pygame
        x, y, onions, cooking_left, ready = pot
        if not (0 <= x < self.grid_width and 0 <= y < self.grid_height):
            return
        px, py = self._grid_to_px(x, y)
        rect = pg.Rect(px + 4, py + 4, self.TILE_SIZE - 8, self.TILE_SIZE - 8)
        if ready:
            color = self.COLORS["pot_ready"]
        elif cooking_left > 0:
            color = self.COLORS["pot_cooking"]
        else:
            color = self.COLORS["pot"]
        pg.draw.rect(self.surface, color, rect, border_radius=8)
        label = f"{onions}/3"
        if cooking_left > 0:
            label += f" t-{cooking_left}"
        if ready:
            label = "READY"
        text_surf = self.font.render(label, True, (10, 10, 10))
        self.surface.blit(text_surf, (px + 8, py + self.TILE_SIZE // 2 - 8))

    def _draw_agent(self, agent_id: str, pos: tuple[int, int], held: str | None) -> None:
        pg = self._pygame
        x, y = pos
        if not (0 <= x < self.grid_width and 0 <= y < self.grid_height):
            return
        px, py = self._grid_to_px(x, y)
        center = (px + self.TILE_SIZE // 2, py + self.TILE_SIZE // 2)
        body_color = self.COLORS.get(agent_id, (160, 160, 160))
        pg.draw.circle(self.surface, body_color, center, self.TILE_SIZE // 3)
        # Held item dot.
        if held:
            held_color = {
                "onion": self.COLORS["onion_held"],
                "dish": self.COLORS["dish_held"],
                "soup": self.COLORS["soup_held"],
            }.get(held, (180, 180, 180))
            pg.draw.circle(
                self.surface, held_color, (center[0], center[1] - self.TILE_SIZE // 4), 8
            )
        # Label.
        label = agent_id.replace("agent_", "A")
        text_surf = self.font.render(label, True, (255, 255, 255))
        self.surface.blit(text_surf, (px + 6, py + 6))

    def _draw_hud(self, info: _RenderInfo, last_reward: float) -> None:
        pg = self._pygame
        hud_top = self.grid_height * self.TILE_SIZE
        hud_rect = pg.Rect(0, hud_top, self._win_w, self.HUD_HEIGHT)
        pg.draw.rect(self.surface, self.COLORS["hud_bg"], hud_rect)

        line1 = (
            f"step {info.timestep}/{info.max_steps}  "
            f"score {info.score:.1f}  soups {info.soup_count}  "
            f"r {last_reward:+.2f}"
        )
        held_summary = ", ".join(
            f"{aid}:{(info.held.get(aid) or '-')}" for aid in sorted(info.held.keys())
        )
        line2 = held_summary or "(no agents)"

        s1 = self.big_font.render(line1, True, self.COLORS["hud_text"])
        s2 = self.font.render(line2, True, self.COLORS["hud_text"])
        self.surface.blit(s1, (8, hud_top + 8))
        self.surface.blit(s2, (8, hud_top + 38))

    def draw(self, env: Any, obs: "EnvObservation", last_reward: float = 0.0) -> None:
        """Render one frame for the current env state.

        ``env`` is used purely for attribute introspection — it must NOT be
        mutated. ``obs`` is the most recent observation returned by the env.
        """
        pg = self._pygame
        info = _extract_render_info(env, obs)
        # Resize the canvas if the env reports different bounds than what we
        # were constructed with.
        if info.grid_width != self.grid_width or info.grid_height != self.grid_height:
            self.grid_width = int(info.grid_width)
            self.grid_height = int(info.grid_height)
            self._win_w = self.grid_width * self.TILE_SIZE
            self._win_h = self.grid_height * self.TILE_SIZE + self.HUD_HEIGHT
            self.surface = pg.display.set_mode((self._win_w, self._win_h))

        self._draw_grid()
        for pot in info.pots:
            self._draw_pot(pot)
        for aid, pos in info.positions.items():
            self._draw_agent(aid, pos, info.held.get(aid))
        self._draw_hud(info, last_reward)

        if not self._headless:
            try:
                pg.display.flip()
            except pg.error:  # pragma: no cover - defensive
                pass
        else:
            # In headless mode we still call update() so that the surface is
            # marked clean; flip() is unnecessary on the dummy driver.
            try:
                pg.display.update()
            except pg.error:  # pragma: no cover - defensive
                pass

    # ------------------------------------------------------------------ events
    def poll_events(self) -> dict[str, Any]:
        """Drain the OS event queue and return a structured snapshot.

        Returns a dict with keys:
          * ``quit`` (bool): user requested exit (window-close, Q, or Esc).
          * ``pressed`` (set[int]): pygame keycodes whose key state is down.
          * ``just_pressed`` (set[int]): keycodes for KEYDOWN events seen
            during this poll (one-shot keys; useful for "interact" toggles).
        """
        pg = self._pygame
        out: dict[str, Any] = {
            "quit": False,
            "pressed": set(),
            "just_pressed": set(),
        }
        for event in pg.event.get():
            if event.type == pg.QUIT:
                out["quit"] = True
            elif event.type == pg.KEYDOWN:
                out["just_pressed"].add(event.key)
                if event.key in (pg.K_q, pg.K_ESCAPE):
                    out["quit"] = True
        try:
            keys = pg.key.get_pressed()
            for code in range(len(keys)):
                if keys[code]:
                    out["pressed"].add(code)
        except pg.error:  # pragma: no cover - headless without keyboard
            pass
        return out

    # ------------------------------------------------------------------- close
    def close(self) -> None:
        """Tear down pygame display and font subsystems."""
        try:
            self._pygame.display.quit()
        except Exception:  # pragma: no cover - defensive
            pass
        try:
            self._pygame.quit()
        except Exception:  # pragma: no cover - defensive
            pass


__all__ = ["PygameRenderer"]
