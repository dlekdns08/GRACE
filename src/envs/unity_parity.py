"""Unity <-> Carroll Python simulation parity verification (Phase G6).

Unity's ``TrajectoryRecorder`` produces JSONL with one record per
``(step, agent)`` interaction::

    {"episode": int, "step": int, "agent_id": "agent_0|agent_1",
     "action": int (0..5), "reward": float, "done": bool,
     "state_text": str}

This module:

1. Parses JSONL into per-episode action sequences.
2. Replays each episode through Carroll's overcooked-ai.
3. Diffs the resulting state texts step-by-step.
4. Reports any divergence as a parity failure.

Carroll action ordering -- verified from
``overcooked_ai_py.mdp.actions.Action.INDEX_TO_ACTION``::

    Direction.NORTH = (0, -1)
    Direction.SOUTH = (0,  1)
    Direction.EAST  = (1,  0)
    Direction.WEST  = (-1, 0)
    STAY            = (0,  0)
    Action.INTERACT = "interact"

    Action.ALL_ACTIONS = [NORTH, SOUTH, EAST, WEST, STAY, INTERACT]
    # i.e. Carroll indices: 0=N, 1=S, 2=E, 3=W, 4=STAY, 5=INTERACT.

GRACE / Unity action enum (locked in ``unity_env/GAME_DESIGN.md`` section 2)::

    0=STAY, 1=N, 2=S, 3=E, 4=W, 5=INTERACT

So the mapping ``GRACE -> Carroll`` is::

    GRACE_TO_CARROLL = {0: 4 (STAY),
                        1: 0 (N), 2: 1 (S), 3: 2 (E), 4: 3 (W),
                        5: 5 (INTERACT)}

The two coincide on INTERACT only. STAY and the four directions are
permuted.
"""

from __future__ import annotations

import difflib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------- action mapping
# GRACE/Unity index -> Carroll INDEX_TO_ACTION index.
GRACE_TO_CARROLL: dict[int, int] = {
    0: 4,  # STAY
    1: 0,  # NORTH
    2: 1,  # SOUTH
    3: 2,  # EAST
    4: 3,  # WEST
    5: 5,  # INTERACT
}

_AGENT_IDS: tuple[str, str] = ("agent_0", "agent_1")


# --------------------------------------------------------------------- dataclasses
@dataclass(slots=True)
class TrajectoryRecord:
    """One JSONL row -- a single (episode, step, agent) interaction."""

    episode: int
    step: int
    agent_id: str
    action: int
    reward: float
    done: bool
    state_text: str


@dataclass(slots=True)
class EpisodeTrajectory:
    """All records belonging to one episode, regrouped by step.

    ``actions[step]`` is the joint action for that step
    (``{"agent_0": int, "agent_1": int}``). ``state_texts[step]`` is the
    Unity-reported text *after* applying ``actions[step]`` -- Unity's
    recorder logs the post-tick state.
    """

    episode: int
    layout: str | None
    actions: list[dict[str, int]]
    state_texts: list[str]
    rewards: list[float]
    done_at: int | None


@dataclass(slots=True)
class ParityDiff:
    """One step where Unity and Carroll disagreed."""

    step: int
    unity_text: str
    carroll_text: str
    diff_lines: list[str]


# --------------------------------------------------------------------- JSONL I/O
def load_jsonl(path: str | Path) -> list[TrajectoryRecord]:
    """Read a Unity-recorded JSONL file into a flat list of records.

    One JSON object per line. Empty lines are tolerated so files appended
    to with trailing newlines do not break loading.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"JSONL trajectory not found: {p}")

    records: list[TrajectoryRecord] = []
    with p.open("r", encoding="utf-8") as fh:
        for lineno, raw_line in enumerate(fh, start=1):
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{p}:{lineno}: invalid JSON: {e}") from e
            try:
                rec = TrajectoryRecord(
                    episode=int(obj["episode"]),
                    step=int(obj["step"]),
                    agent_id=str(obj["agent_id"]),
                    action=int(obj["action"]),
                    reward=float(obj["reward"]),
                    done=bool(obj["done"]),
                    state_text=str(obj["state_text"]),
                )
            except KeyError as e:
                raise ValueError(
                    f"{p}:{lineno}: JSONL row missing required field {e!s}"
                ) from e
            records.append(rec)
    return records


def group_into_episodes(
    records: list[TrajectoryRecord], n_agents: int = 2
) -> list[EpisodeTrajectory]:
    """Group records by ``episode`` -> ``step`` -> per-agent.

    Validates that every ``(episode, step)`` cell contains exactly
    ``n_agents`` rows (one per expected agent). Raises ``ValueError`` if
    not -- a malformed JSONL almost always means recording was
    interrupted, and proceeding silently would corrupt the parity check.

    Output episodes are sorted by ``episode`` index; steps within each
    episode are sorted by ``step``. The reward at each step is the sum
    over agents (Carroll reports a shared reward; per-agent rows in the
    JSONL store the same value duplicated, but summing tolerates either
    convention).
    """
    if n_agents <= 0:
        raise ValueError(f"n_agents must be positive; got {n_agents}")

    expected_agents = list(_AGENT_IDS[:n_agents]) if n_agents <= len(_AGENT_IDS) else None

    # episode -> step -> agent_id -> TrajectoryRecord
    grouped: dict[int, dict[int, dict[str, TrajectoryRecord]]] = {}
    for rec in records:
        grouped.setdefault(rec.episode, {}).setdefault(rec.step, {})
        if rec.agent_id in grouped[rec.episode][rec.step]:
            raise ValueError(
                f"duplicate agent row: episode={rec.episode} step={rec.step} "
                f"agent_id={rec.agent_id}"
            )
        grouped[rec.episode][rec.step][rec.agent_id] = rec

    episodes: list[EpisodeTrajectory] = []
    for ep_id in sorted(grouped):
        steps_dict = grouped[ep_id]
        actions: list[dict[str, int]] = []
        state_texts: list[str] = []
        rewards: list[float] = []
        done_at: int | None = None

        for step_id in sorted(steps_dict):
            agents = steps_dict[step_id]
            if len(agents) != n_agents:
                raise ValueError(
                    f"episode {ep_id} step {step_id}: expected {n_agents} agent "
                    f"rows, got {len(agents)} ({sorted(agents)})"
                )
            if expected_agents is not None:
                missing = [a for a in expected_agents if a not in agents]
                if missing:
                    raise ValueError(
                        f"episode {ep_id} step {step_id}: missing agent rows "
                        f"{missing} (got {sorted(agents)})"
                    )

            # Joint action.
            joint: dict[str, int] = {aid: int(rec.action) for aid, rec in agents.items()}
            actions.append(joint)

            # Use a canonical agent's state_text; Unity records the same
            # post-tick state on every per-agent row so any will do. We
            # prefer agent_0 if present, else the first sorted agent.
            canonical = agents.get("agent_0") or agents[sorted(agents)[0]]
            state_texts.append(canonical.state_text)

            step_reward = float(sum(rec.reward for rec in agents.values()))
            rewards.append(step_reward)

            if done_at is None and any(rec.done for rec in agents.values()):
                done_at = int(step_id)

        episodes.append(
            EpisodeTrajectory(
                episode=int(ep_id),
                layout=None,
                actions=actions,
                state_texts=state_texts,
                rewards=rewards,
                done_at=done_at,
            )
        )

    return episodes


# --------------------------------------------------------------- parquet export
def jsonl_to_parquet(
    jsonl_path: str | Path, parquet_path: str | Path
) -> int:
    """Convert a Unity JSONL trajectory to parquet for downstream BC training.

    Output schema mirrors what ``src.training.bc.load_demos_to_dataset``
    expects (``REQUIRED_COLUMNS``) plus a ``raw_obs`` placeholder.

    Columns:
        episode (int64), step (int64), agent_id (string),
        action (int64), reward (float64), done (bool),
        state_text (string), raw_obs (object/None), source (string="human_unity").

    ``raw_obs`` is set to ``None`` because Unity's TrajectoryRecorder
    does not currently emit raw feature vectors -- BC training from Unity
    demos requires re-deriving observations later or skipping this column
    entirely. Returns the number of rows written.
    """
    import pandas as pd

    records = load_jsonl(jsonl_path)
    if not records:
        raise ValueError(f"{jsonl_path}: no records found")

    rows: list[dict[str, Any]] = []
    for rec in records:
        rows.append(
            {
                "episode": int(rec.episode),
                "step": int(rec.step),
                "agent_id": str(rec.agent_id),
                "action": int(rec.action),
                "reward": float(rec.reward),
                "done": bool(rec.done),
                "state_text": str(rec.state_text),
                "raw_obs": None,
                "source": "human_unity",
            }
        )

    df = pd.DataFrame(rows)
    out_path = Path(parquet_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path, index=False)
    return len(df)


# ----------------------------------------------------------------- Carroll replay
def replay_through_carroll(
    traj: EpisodeTrajectory,
    layout: str,
    horizon: int = 400,
) -> list[str]:
    """Replay the action sequence in ``traj`` through Carroll's overcooked-ai.

    Returns one post-tick ``state_text`` per recorded step, using the
    same formatter that ``src.envs.python_env`` uses (so the strings are
    directly comparable to Unity's). If ``overcooked_ai_py`` is not
    installed, logs a warning and returns an empty list -- callers are
    expected to detect this and skip parity verification gracefully.
    """
    try:
        from overcooked_ai_py.mdp.actions import Action
        from overcooked_ai_py.mdp.overcooked_env import OvercookedEnv as CarrollEnv
        from overcooked_ai_py.mdp.overcooked_mdp import OvercookedGridworld
    except ImportError:
        _log.warning(
            "overcooked_ai_py is not installed; cannot replay through Carroll."
        )
        return []

    # Lazy import so the module loads even if python_env's heavier deps
    # are unavailable; the formatter itself is pure-Python.
    from src.envs.python_env import _carroll_state_to_text

    mdp = OvercookedGridworld.from_layout_name(layout)
    env = CarrollEnv.from_mdp(mdp, horizon=int(horizon))
    env.reset()

    texts: list[str] = []
    for step_idx, joint in enumerate(traj.actions):
        # Translate GRACE indices -> Carroll INDEX_TO_ACTION indices.
        try:
            carroll_idxs = tuple(GRACE_TO_CARROLL[int(joint[aid])] for aid in _AGENT_IDS)
        except KeyError as e:
            raise ValueError(
                f"episode {traj.episode} step {step_idx}: invalid GRACE action "
                f"{e!s} -- expected 0..5"
            ) from e
        joint_action = tuple(Action.INDEX_TO_ACTION[i] for i in carroll_idxs)

        env.step(joint_action)
        texts.append(_carroll_state_to_text(env.state, mdp, int(horizon)))

        # Stop replaying past Unity's reported episode end -- Carroll may
        # auto-reset on done in some configurations, which would garble
        # later texts. We compare only as far as Unity recorded.
        if traj.done_at is not None and step_idx >= traj.done_at:
            break

    return texts


# -------------------------------------------------------------------- diff utils
def diff_episode(
    traj: EpisodeTrajectory, carroll_texts: list[str]
) -> list[ParityDiff]:
    """Pairwise compare Unity vs Carroll state texts for one episode.

    Returns only the steps that differ. An empty list means perfect
    parity. If the two lists have different lengths, the overlapping
    prefix is compared and the trailing tail is reported as one big diff
    on the next step boundary.
    """
    diffs: list[ParityDiff] = []
    n = min(len(traj.state_texts), len(carroll_texts))
    for i in range(n):
        unity_text = traj.state_texts[i]
        carroll_text = carroll_texts[i]
        if unity_text == carroll_text:
            continue
        diff_lines = list(
            difflib.unified_diff(
                unity_text.splitlines(),
                carroll_text.splitlines(),
                fromfile=f"unity[step={i}]",
                tofile=f"carroll[step={i}]",
                lineterm="",
            )
        )
        diffs.append(
            ParityDiff(
                step=i,
                unity_text=unity_text,
                carroll_text=carroll_text,
                diff_lines=diff_lines,
            )
        )

    # Trailing length mismatch: report the missing-side as a synthetic
    # diff at the boundary so the parity report cannot hide it.
    if len(traj.state_texts) != len(carroll_texts):
        boundary = n
        unity_tail = (
            traj.state_texts[boundary] if boundary < len(traj.state_texts) else "<absent>"
        )
        carroll_tail = (
            carroll_texts[boundary] if boundary < len(carroll_texts) else "<absent>"
        )
        diff_lines = list(
            difflib.unified_diff(
                unity_tail.splitlines(),
                carroll_tail.splitlines(),
                fromfile=f"unity[step={boundary}]",
                tofile=f"carroll[step={boundary}]",
                lineterm="",
            )
        )
        diffs.append(
            ParityDiff(
                step=boundary,
                unity_text=unity_tail,
                carroll_text=carroll_tail,
                diff_lines=diff_lines,
            )
        )

    return diffs


def parity_summary(diffs: list[ParityDiff], total_steps: int) -> dict[str, Any]:
    """Aggregate stats over a single episode's diff list.

    Returns ``n_steps_total``, ``n_steps_diff``, ``first_diff_step``
    (``None`` on perfect parity) and ``parity_rate`` in [0, 1].
    """
    total = int(max(total_steps, 0))
    n_diff = int(len(diffs))
    first = int(diffs[0].step) if diffs else None
    if total == 0:
        rate = 1.0 if n_diff == 0 else 0.0
    else:
        # Clamp to [0, 1] in case a length-mismatch diff pushes n_diff
        # one above total (boundary diff).
        rate = max(0.0, min(1.0, 1.0 - (n_diff / total)))
    return {
        "n_steps_total": total,
        "n_steps_diff": n_diff,
        "first_diff_step": first,
        "parity_rate": float(rate),
    }


__all__ = [
    "EpisodeTrajectory",
    "GRACE_TO_CARROLL",
    "ParityDiff",
    "TrajectoryRecord",
    "diff_episode",
    "group_into_episodes",
    "jsonl_to_parquet",
    "load_jsonl",
    "parity_summary",
    "replay_through_carroll",
]
