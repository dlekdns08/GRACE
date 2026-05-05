"""Interactive human-play renderer for Overcooked-style envs (Phase 9).

Modes:

  * ``solo``      — agent_0 keyboard, agent_1 noop.
  * ``coop``      — agent_0 = WASD/Space/E, agent_1 = arrows/RShift/RCtrl.
  * ``vs_policy`` — agent_0 keyboard, agent_1 = loaded PPO checkpoint.
  * ``vs_llm``    — agent_0 keyboard, agent_1 = LLMAugmentedPPOPolicy with
                    FixedKMetaPolicy(k=20) and a Mock or LM Studio LLM.

Recording:
  When ``--record path.parquet`` is set, every env step writes one row
  per agent with columns ``(episode, step, agent_id, raw_obs, action,
  reward, done, source)``. Rows accumulate in memory and flush at session
  exit (or after every episode via ``--flush-every-episode``).

Use:

  .venv/bin/python scripts/play_human.py --env dummy --mode solo
  .venv/bin/python scripts/play_human.py --env dummy --mode coop \\
      --record demos/run1.parquet --max-fps 8
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path
from typing import Any

# Allow running as `python scripts/play_human.py` from repo root.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import numpy as np  # noqa: E402

from src.envs import DummyOvercookedEnv, OvercookedEnv  # noqa: E402
from src.envs.base import EnvObservation  # noqa: E402
from src.policies.base import PolicyContext  # noqa: E402

_log = logging.getLogger("play_human")

# ----------------------------------------------------------------------- actions
# Match DummyOvercookedEnv (and Carroll's overcooked-ai) discrete actions:
# 0=noop, 1=up, 2=down, 3=left, 4=right, 5=interact.
ACTION_NOOP = 0
ACTION_UP = 1
ACTION_DOWN = 2
ACTION_LEFT = 3
ACTION_RIGHT = 4
ACTION_INTERACT = 5


def _make_env(env_name: str, horizon: int) -> OvercookedEnv:
    if env_name == "dummy":
        return DummyOvercookedEnv(max_steps=int(horizon))
    if env_name == "cramped_room":
        from src.envs.python_env import PythonOvercookedEnv

        return PythonOvercookedEnv(layout_name="cramped_room", horizon=int(horizon))
    raise ValueError(f"Unknown --env {env_name!r}; expected one of: dummy, cramped_room")


def _grid_size(env: OvercookedEnv) -> tuple[int, int]:
    if isinstance(env, DummyOvercookedEnv):
        return 5, 5
    # Best-effort: PythonOvercookedEnv exposes the underlying mdp via _mdp.
    mdp = getattr(env, "_mdp", None)
    if mdp is not None and hasattr(mdp, "width") and hasattr(mdp, "height"):
        return int(mdp.width), int(mdp.height)
    return 5, 5


# ----------------------------------------------------------------------- keymaps
def _agent0_action(pressed: set[int], just_pressed: set[int]) -> int:
    """WASD movement, Space = interact, E = interact (alt)."""
    import pygame

    if pygame.K_SPACE in just_pressed or pygame.K_e in just_pressed:
        return ACTION_INTERACT
    if pygame.K_w in pressed:
        return ACTION_UP
    if pygame.K_s in pressed:
        return ACTION_DOWN
    if pygame.K_a in pressed:
        return ACTION_LEFT
    if pygame.K_d in pressed:
        return ACTION_RIGHT
    return ACTION_NOOP


def _agent1_action(pressed: set[int], just_pressed: set[int]) -> int:
    """Arrows movement, RShift = interact, RCtrl = interact (alt)."""
    import pygame

    if pygame.K_RSHIFT in just_pressed or pygame.K_RCTRL in just_pressed:
        return ACTION_INTERACT
    if pygame.K_UP in pressed:
        return ACTION_UP
    if pygame.K_DOWN in pressed:
        return ACTION_DOWN
    if pygame.K_LEFT in pressed:
        return ACTION_LEFT
    if pygame.K_RIGHT in pressed:
        return ACTION_RIGHT
    return ACTION_NOOP


# ----------------------------------------------------------------------- recorder
class _DemoRecorder:
    """In-memory buffer of demo rows with a final parquet flush.

    The schema mirrors what ``load_demos_to_dataset`` expects:
    ``(episode, step, agent_id, raw_obs, action, reward, done, source)``.
    Rows are stored as plain dicts; pandas converts the ``raw_obs`` lists
    to a list-typed column when the parquet is written.
    """

    def __init__(self, path: Path | None) -> None:
        self.path: Path | None = path
        self.rows: list[dict[str, Any]] = []

    def log(
        self,
        episode: int,
        step: int,
        agent_id: str,
        raw_obs: np.ndarray,
        action: int,
        reward: float,
        done: bool,
        source: str,
    ) -> None:
        if self.path is None:
            return
        self.rows.append(
            {
                "episode": int(episode),
                "step": int(step),
                "agent_id": str(agent_id),
                "raw_obs": np.asarray(raw_obs, dtype=np.float32).tolist(),
                "action": int(action),
                "reward": float(reward),
                "done": bool(done),
                "source": str(source),
            }
        )

    def flush(self) -> Path | None:
        if self.path is None or not self.rows:
            return None
        import pandas as pd

        self.path.parent.mkdir(parents=True, exist_ok=True)
        df = pd.DataFrame(self.rows)
        df.to_parquet(self.path, index=False)
        _log.info("wrote %d demo rows to %s", len(df), self.path)
        return self.path


# ----------------------------------------------------------------------- mode setup
def _build_agent1_controller(
    args: argparse.Namespace, env: OvercookedEnv
) -> tuple[Any, str]:
    """Return ``(controller, source_label)`` for the non-keyboard agent.

    ``controller`` is one of:
      * ``"keyboard"`` (string sentinel) — both agent_1 and agent_0 read keys.
      * ``"noop"`` — always emits action 0.
      * a callable ``ctx -> dict[str, int]`` that returns a joint action;
        the caller picks out the agent_1 entry.
    """
    mode = args.mode
    if mode == "solo":
        return "noop", "noop"
    if mode == "coop":
        return "keyboard", "human"
    if mode == "vs_policy":
        if not args.checkpoint:
            raise ValueError("vs_policy mode requires --checkpoint")
        import torch

        from src.policies import PPOPolicy

        ckpt = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
        state_dict = ckpt["state_dict"] if isinstance(ckpt, dict) and "state_dict" in ckpt else ckpt
        policy = PPOPolicy(
            obs_dim=env.obs_dim,
            action_dim=env.action_space_size,
            hidden_dim=int(args.hidden_dim),
            n_layers=int(args.n_layers),
        )
        try:
            policy.load_state_dict(state_dict)
        except Exception as exc:  # pragma: no cover - depends on user ckpt
            _log.warning("load_state_dict partial: %s", exc)
        policy.set_sampling(False)  # deterministic during play
        return policy, "policy"
    if mode == "vs_llm":
        from src.llm import MockLLMClient
        from src.policies import FixedKMetaPolicy, LLMAugmentedPPOPolicy

        llm: Any
        if args.llm == "mock":
            llm = MockLLMClient(
                [
                    '{"agent_0": "go_to_onion", "agent_1": "go_to_onion"}',
                    '{"agent_0": "deliver_onion_to_pot", "agent_1": "pickup_dish"}',
                ]
            )
        elif args.llm == "lmstudio":  # pragma: no cover - requires local server
            from src.llm import LMStudioClient

            llm = LMStudioClient(base_url=args.llm_base_url, model=args.llm_model)
        else:
            raise ValueError(f"Unknown --llm {args.llm!r}")

        meta = FixedKMetaPolicy(k=int(args.llm_k))
        policy = LLMAugmentedPPOPolicy(
            obs_dim=env.obs_dim,
            action_dim=env.action_space_size,
            hidden_dim=int(args.hidden_dim),
            n_layers=int(args.n_layers),
        )
        if args.checkpoint:  # optional warm-start
            import torch

            ckpt = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
            sd = ckpt["state_dict"] if isinstance(ckpt, dict) and "state_dict" in ckpt else ckpt
            try:
                policy.load_state_dict(sd, strict=False)
            except Exception as exc:  # pragma: no cover - user ckpt
                _log.warning("vs_llm load_state_dict partial: %s", exc)
        policy.set_sampling(False)

        return _LLMAugmentedDriver(policy, meta, llm), "llm_augmented"

    raise ValueError(f"Unknown mode: {mode!r}")


class _LLMAugmentedDriver:
    """Bundles policy + meta + LLM into a single ctx -> joint-action callable.

    State (current_subgoal, steps_since_call, episode_step) is owned by
    this helper instead of the rollout loop because the play script
    interleaves human and policy actions on a per-frame basis.
    """

    def __init__(self, policy: Any, meta: Any, llm: Any) -> None:
        from src.llm import build_request, parse_subgoal

        self._policy = policy
        self._meta = meta
        self._llm = llm
        self._build_request = build_request
        self._parse_subgoal = parse_subgoal
        self.current_subgoal: dict[str, str] | None = None
        self.steps_since_llm_call: int = 0
        self.episode_step: int = 0

    def reset(self) -> None:
        self.current_subgoal = None
        self.steps_since_llm_call = 0
        self.episode_step = 0
        if hasattr(self._meta, "reset"):
            self._meta.reset()

    def __call__(self, obs: EnvObservation, agent_ids: list[str]) -> dict[str, int]:
        ctx = PolicyContext(
            obs=obs,
            current_subgoal=self.current_subgoal,
            steps_since_llm_call=self.steps_since_llm_call,
            episode_step=self.episode_step,
        )
        if bool(self._meta.should_call_llm(ctx)):
            from src.llm import LLMRequest  # noqa: F401  (typing only)

            req = self._build_request(obs.text, agent_ids)
            try:
                resp = self._llm.call(req)
                parsed = self._parse_subgoal(resp.text)
                if parsed is not None:
                    self.current_subgoal = parsed
            except Exception as exc:  # pragma: no cover - user LLM
                _log.warning("LLM call failed (%s); keeping prior subgoal", exc)
            self.steps_since_llm_call = 0
        else:
            self.steps_since_llm_call += 1
        actions = self._policy.act(ctx)
        self.episode_step += 1
        return actions


# ----------------------------------------------------------------------- main loop
def run_session(args: argparse.Namespace) -> None:
    from src.envs.render_pygame import PygameRenderer

    env = _make_env(args.env, horizon=int(args.horizon))
    grid_w, grid_h = _grid_size(env)
    renderer = PygameRenderer(width=grid_w, height=grid_h, headless=False)

    controller, agent1_source = _build_agent1_controller(args, env)
    recorder = _DemoRecorder(Path(args.record) if args.record else None)

    target_dt = 1.0 / max(float(args.max_fps), 1.0)
    episode = 0
    quit_requested = False

    try:
        while not quit_requested:
            obs = env.reset(seed=args.seed if args.seed >= 0 else None)
            renderer.draw(env, obs, last_reward=0.0)
            ep_return = 0.0
            ep_steps = 0
            ep_soup = 0
            done = False
            if isinstance(controller, _LLMAugmentedDriver):
                controller.reset()

            while not done:
                frame_start = time.perf_counter()
                events = renderer.poll_events()
                if events["quit"]:
                    quit_requested = True
                    break

                pressed = events["pressed"]
                just = events["just_pressed"]
                a0 = _agent0_action(pressed, just)

                # agent_1 controller dispatch.
                if controller == "keyboard":
                    a1 = _agent1_action(pressed, just)
                    a1_source = "human"
                elif controller == "noop":
                    a1 = ACTION_NOOP
                    a1_source = "noop"
                elif isinstance(controller, _LLMAugmentedDriver):
                    actions = controller(obs, list(env.agent_ids))
                    a1 = int(actions.get("agent_1", ACTION_NOOP))
                    a1_source = agent1_source
                else:
                    # PPOPolicy or compatible.
                    ctx = PolicyContext(
                        obs=obs, current_subgoal=None, steps_since_llm_call=0, episode_step=ep_steps
                    )
                    actions = controller.act(ctx)
                    a1 = int(actions.get("agent_1", ACTION_NOOP))
                    a1_source = agent1_source

                joint = {"agent_0": int(a0), "agent_1": int(a1)}
                step = env.step(joint)
                done = bool(step.terminated or step.truncated)
                r0 = float(step.rewards.get("agent_0", 0.0))
                r1 = float(step.rewards.get("agent_1", 0.0))
                ep_return += r0 + r1
                ep_soup = int(step.info.get("soup_count", ep_soup))

                # Record demo rows.
                if recorder.path is not None:
                    recorder.log(
                        episode, ep_steps, "agent_0",
                        obs.raw["agent_0"], a0, r0, done, "human",
                    )
                    recorder.log(
                        episode, ep_steps, "agent_1",
                        obs.raw["agent_1"], a1, r1, done, a1_source,
                    )

                obs = step.obs
                ep_steps += 1
                renderer.draw(env, obs, last_reward=r0 + r1)

                # Frame pacing.
                elapsed = time.perf_counter() - frame_start
                if elapsed < target_dt:
                    time.sleep(target_dt - elapsed)

            print(
                f"Episode {episode}: return={ep_return:.2f}  steps={ep_steps}  soups={ep_soup}"
            )
            if args.flush_every_episode:
                recorder.flush()
            episode += 1

            if quit_requested:
                break
            if args.max_episodes > 0 and episode >= args.max_episodes:
                break

            # Ask whether to continue. In headless / non-interactive sessions
            # the user can pre-set --max-episodes and avoid this prompt entirely.
            try:
                ans = input("Play again? [y/n] ").strip().lower()
            except EOFError:
                ans = "n"
            if ans not in ("y", "yes", ""):
                break
    finally:
        recorder.flush()
        try:
            renderer.close()
        except Exception:  # pragma: no cover - defensive
            pass
        try:
            env.close()
        except Exception:  # pragma: no cover - defensive
            pass


# --------------------------------------------------------------------------- CLI
def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="play_human",
        description="Interactive Overcooked human-play with optional demo recording.",
    )
    p.add_argument("--env", default="dummy", choices=["dummy", "cramped_room"])
    p.add_argument(
        "--mode",
        default="solo",
        choices=["solo", "coop", "vs_policy", "vs_llm"],
    )
    p.add_argument("--horizon", type=int, default=200)
    p.add_argument("--seed", type=int, default=-1, help=">= 0 to set; negative for unseeded")
    p.add_argument("--max-fps", dest="max_fps", type=float, default=10.0)
    p.add_argument("--max-episodes", dest="max_episodes", type=int, default=0,
                   help="Auto-exit after N episodes (0 = unlimited / prompt each time)")
    p.add_argument("--record", default=None, help="Parquet path to record demos to")
    p.add_argument("--flush-every-episode", action="store_true",
                   help="Flush recorder after each episode (otherwise only at exit)")
    p.add_argument("--checkpoint", default=None,
                   help="PPO checkpoint for vs_policy / vs_llm modes")
    p.add_argument("--hidden-dim", dest="hidden_dim", type=int, default=128)
    p.add_argument("--n-layers", dest="n_layers", type=int, default=2)
    p.add_argument("--llm", default="mock", choices=["mock", "lmstudio"])
    p.add_argument("--llm-base-url", dest="llm_base_url", default="http://localhost:1234/v1")
    p.add_argument("--llm-model", dest="llm_model", default="qwen-mock")
    p.add_argument("--llm-k", dest="llm_k", type=int, default=20,
                   help="FixedKMetaPolicy period for vs_llm mode")
    p.add_argument("--log-level", default="INFO")
    return p


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))
    run_session(args)


if __name__ == "__main__":  # pragma: no cover - manual entry point
    main()
