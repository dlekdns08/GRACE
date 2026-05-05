"""Tests for the Unity <-> Carroll parity utilities (Phase G6).

These tests do not require Unity. JSONL fixtures are fabricated by hand
or via the in-memory ``DummyOvercookedEnv``; the optional Carroll replay
is exercised separately and gracefully skipped when ``overcooked_ai_py``
is not installed.
"""

from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.envs.unity_parity import (
    GRACE_TO_CARROLL,
    EpisodeTrajectory,
    ParityDiff,
    diff_episode,
    group_into_episodes,
    jsonl_to_parquet,
    load_jsonl,
    parity_summary,
    replay_through_carroll,
)


# ----------------------------------------------------------------------- helpers
def _row(
    *,
    episode: int,
    step: int,
    agent_id: str,
    action: int,
    reward: float = 0.0,
    done: bool = False,
    state_text: str = "Step: 0/400\nScore: 0\n",
) -> dict[str, Any]:
    return {
        "episode": int(episode),
        "step": int(step),
        "agent_id": str(agent_id),
        "action": int(action),
        "reward": float(reward),
        "done": bool(done),
        "state_text": str(state_text),
    }


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")


def _fabricate_jsonl(
    path: Path,
    n_episodes: int = 2,
    n_steps: int = 5,
    state_text_fn: Any = None,
) -> list[dict[str, Any]]:
    """Build a regular n_episodes x n_steps x 2-agent JSONL fixture."""

    def default_text(ep: int, step: int) -> str:
        return f"Step: {step}/400\nScore: 0\nepisode={ep}\n"

    fn = state_text_fn or default_text
    rows: list[dict[str, Any]] = []
    for ep in range(n_episodes):
        for step in range(n_steps):
            for aid in ("agent_0", "agent_1"):
                rows.append(
                    _row(
                        episode=ep,
                        step=step,
                        agent_id=aid,
                        action=(step % 6),
                        reward=0.0,
                        done=(step == n_steps - 1),
                        state_text=fn(ep, step),
                    )
                )
    _write_jsonl(path, rows)
    return rows


# ----------------------------------------------------------------------- tests
def test_grace_to_carroll_mapping_indices() -> None:
    """GRACE 0..5 must map onto Carroll's INDEX_TO_ACTION 0..5 exactly once."""
    assert sorted(GRACE_TO_CARROLL.keys()) == [0, 1, 2, 3, 4, 5]
    assert sorted(GRACE_TO_CARROLL.values()) == [0, 1, 2, 3, 4, 5]
    # INTERACT is the only fixed point.
    assert GRACE_TO_CARROLL[5] == 5
    # STAY in GRACE (0) is at index 4 in Carroll.
    assert GRACE_TO_CARROLL[0] == 4


def test_load_jsonl_round_trip(tmp_path: Path) -> None:
    """Write a JSONL fixture, load it, assert records match input."""
    rows = _fabricate_jsonl(tmp_path / "demo.jsonl", n_episodes=1, n_steps=3)
    records = load_jsonl(tmp_path / "demo.jsonl")
    assert len(records) == len(rows)
    for rec, row in zip(records, rows, strict=True):
        assert rec.episode == row["episode"]
        assert rec.step == row["step"]
        assert rec.agent_id == row["agent_id"]
        assert rec.action == row["action"]
        assert rec.reward == row["reward"]
        assert rec.done == row["done"]
        assert rec.state_text == row["state_text"]


def test_load_jsonl_tolerates_blank_lines(tmp_path: Path) -> None:
    """Blank lines mid-file should not break the loader."""
    p = tmp_path / "demo.jsonl"
    p.write_text(
        json.dumps(_row(episode=0, step=0, agent_id="agent_0", action=0)) + "\n"
        "\n"
        + json.dumps(_row(episode=0, step=0, agent_id="agent_1", action=0)) + "\n",
        encoding="utf-8",
    )
    records = load_jsonl(p)
    assert len(records) == 2


def test_load_jsonl_missing_field_raises(tmp_path: Path) -> None:
    p = tmp_path / "bad.jsonl"
    p.write_text(json.dumps({"episode": 0, "step": 0}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_jsonl(p)


def test_group_into_episodes_basic(tmp_path: Path) -> None:
    """2 episodes x 5 steps x 2 agents -> 20 rows -> 2 EpisodeTrajectories."""
    _fabricate_jsonl(tmp_path / "demo.jsonl", n_episodes=2, n_steps=5)
    records = load_jsonl(tmp_path / "demo.jsonl")
    assert len(records) == 20

    episodes = group_into_episodes(records, n_agents=2)
    assert len(episodes) == 2
    for traj in episodes:
        assert isinstance(traj, EpisodeTrajectory)
        assert len(traj.actions) == 5
        assert len(traj.state_texts) == 5
        assert len(traj.rewards) == 5
        assert traj.done_at == 4
        for joint in traj.actions:
            assert set(joint.keys()) == {"agent_0", "agent_1"}


def test_group_validates_agent_count(tmp_path: Path) -> None:
    """If a step is missing one agent's row, grouping must raise."""
    rows = _fabricate_jsonl(tmp_path / "demo.jsonl", n_episodes=1, n_steps=5)
    # Drop the agent_1 row for step 3.
    rows = [
        r
        for r in rows
        if not (r["step"] == 3 and r["agent_id"] == "agent_1")
    ]
    _write_jsonl(tmp_path / "demo.jsonl", rows)
    records = load_jsonl(tmp_path / "demo.jsonl")
    with pytest.raises(ValueError, match="step 3"):
        group_into_episodes(records, n_agents=2)


def test_group_rejects_duplicate_agent_row(tmp_path: Path) -> None:
    """A duplicate (episode, step, agent_id) triple should raise."""
    rows = _fabricate_jsonl(tmp_path / "demo.jsonl", n_episodes=1, n_steps=2)
    # Append a duplicate of the first row.
    rows.append(rows[0])
    _write_jsonl(tmp_path / "demo.jsonl", rows)
    records = load_jsonl(tmp_path / "demo.jsonl")
    with pytest.raises(ValueError, match="duplicate"):
        group_into_episodes(records, n_agents=2)


def test_jsonl_to_parquet_schema(tmp_path: Path) -> None:
    """Parquet output must contain the BC-required columns plus our extras."""
    _fabricate_jsonl(tmp_path / "demo.jsonl", n_episodes=1, n_steps=3)
    out = tmp_path / "demo.parquet"
    n = jsonl_to_parquet(tmp_path / "demo.jsonl", out)
    assert n == 6  # 1 episode * 3 steps * 2 agents
    assert out.exists()

    df = pd.read_parquet(out)
    expected = {
        "episode",
        "step",
        "agent_id",
        "action",
        "reward",
        "done",
        "state_text",
        "raw_obs",
        "source",
    }
    assert expected.issubset(set(df.columns))
    assert (df["source"] == "human_unity").all()
    # raw_obs is a placeholder until Unity emits raw observations.
    assert df["raw_obs"].isna().all()
    # Dtypes the BC loader cares about.
    assert df["episode"].dtype.kind in ("i", "u")
    assert df["step"].dtype.kind in ("i", "u")
    assert df["action"].dtype.kind in ("i", "u")
    assert df["done"].dtype == bool


def _make_traj(state_texts: list[str], actions_per_step: int = 0) -> EpisodeTrajectory:
    return EpisodeTrajectory(
        episode=0,
        layout=None,
        actions=[
            {"agent_0": actions_per_step, "agent_1": actions_per_step}
            for _ in state_texts
        ],
        state_texts=list(state_texts),
        rewards=[0.0] * len(state_texts),
        done_at=None,
    )


def test_diff_returns_empty_on_match() -> None:
    texts = ["a", "b", "c"]
    traj = _make_traj(texts)
    assert diff_episode(traj, list(texts)) == []


def test_diff_finds_mismatch() -> None:
    unity_texts = ["state-0", "state-1", "state-2"]
    carroll_texts = ["state-0", "state-1-changed", "state-2"]
    traj = _make_traj(unity_texts)
    diffs = diff_episode(traj, carroll_texts)
    assert len(diffs) == 1
    assert diffs[0].step == 1
    assert "state-1-changed" in "\n".join(diffs[0].diff_lines)


def test_diff_reports_length_mismatch() -> None:
    """If Carroll has fewer steps than Unity, the boundary is reported."""
    traj = _make_traj(["a", "b", "c"])
    diffs = diff_episode(traj, ["a", "b"])  # one shorter
    assert len(diffs) == 1
    assert diffs[0].step == 2
    assert "<absent>" in diffs[0].carroll_text


def test_parity_summary_perfect_match() -> None:
    summary = parity_summary([], total_steps=10)
    assert summary["n_steps_total"] == 10
    assert summary["n_steps_diff"] == 0
    assert summary["first_diff_step"] is None
    assert summary["parity_rate"] == 1.0


def test_parity_summary_with_diffs() -> None:
    diffs = [
        ParityDiff(step=2, unity_text="x", carroll_text="y", diff_lines=[]),
        ParityDiff(step=7, unity_text="x", carroll_text="y", diff_lines=[]),
    ]
    summary = parity_summary(diffs, total_steps=10)
    assert summary["n_steps_total"] == 10
    assert summary["n_steps_diff"] == 2
    assert summary["first_diff_step"] == 2
    assert summary["parity_rate"] == pytest.approx(0.8)


def test_parity_summary_zero_steps() -> None:
    """Edge case: zero steps and zero diffs is treated as perfect parity."""
    summary = parity_summary([], total_steps=0)
    assert summary["parity_rate"] == 1.0


def test_replay_skipped_when_overcooked_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    """If ``overcooked_ai_py`` import fails inside replay, return [] and warn."""
    real_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("overcooked_ai_py"):
            raise ImportError("simulated absence")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    traj = _make_traj(["x", "y"], actions_per_step=0)
    result = replay_through_carroll(traj, layout="cramped_room")
    assert result == []
