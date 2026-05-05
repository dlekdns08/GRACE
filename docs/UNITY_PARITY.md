# Unity <-> Carroll Python Parity (Phase G6)

This document explains why simulation parity matters for GRACE, how to
record a Unity session, and how to verify state-by-state that Unity's
`ChefSimulation` matches Carroll's `overcooked-ai` Python reference.

## Why parity matters

GRACE is a research project. Two execution paths share the same game
logic:

- **Unity** (`unity_env/Assets/Scripts/Core/ChefSimulation.cs`) for human
  play, online co-op via NGO, and ML-Agents training.
- **Python** (`overcooked_ai_py`, wrapped by `src/envs/python_env.py`)
  for fast headless RL training and LLM-in-the-loop debugging.

If the two simulators diverge by even one tile or one tick, the
following all break:

1. **Demonstration data is not portable.** Human plays recorded in Unity
   cannot warm-start a PPO that trains on the Python env (the action
   sequence produces different states).
2. **BC checkpoints don't transfer.** A policy trained on Python states
   produces wrong outputs on Unity states.
3. **Cross-validation between paths is impossible.** We can't sanity
   check Unity by running the Python env on the same trajectory.

So we treat **Carroll as ground truth** and verify Unity matches it
bit-for-bit on every supported layout.

The contract is locked in `unity_env/GAME_DESIGN.md` section 2:
six actions (`0=STAY, 1=N, 2=S, 3=E, 4=W, 5=INTERACT`), shared reward
(+20 per soup served), and Carroll's standard layouts.

## Recording a Unity session

Phase G1 (Unity rewrite) ships a `TrajectoryRecorder` that writes one
JSONL row per `(step, agent)` interaction:

```json
{"episode": 0, "step": 0, "agent_id": "agent_0", "action": 1, "reward": 0.0, "done": false, "state_text": "Step: 1/400\nScore: 0 (soups served: 0)\n..."}
{"episode": 0, "step": 0, "agent_id": "agent_1", "action": 5, "reward": 0.0, "done": false, "state_text": "Step: 1/400\nScore: 0 (soups served: 0)\n..."}
```

Required fields per row: `episode`, `step`, `agent_id`, `action`,
`reward`, `done`, `state_text`. The `state_text` is the **post-tick**
state -- i.e. the state after `actions[step]` has been applied -- and
must use the deterministic format produced by Unity's
`StateSerializer.cs` (kept in lockstep with `src/envs/state_text.py`,
both pinned to `STATE_TEXT_VERSION = "v1"`).

Save the file under `demos/`, e.g. `demos/session_cramped_2026-05-05.jsonl`.

## Verifying parity

The verification is fully Python-side and offline; no Unity runtime
needed once the JSONL has been recorded.

### 1. Convert to parquet (optional but useful)

If you also want to feed these demos into BC training:

```bash
python scripts/jsonl_to_parquet.py \
    demos/session_cramped_2026-05-05.jsonl \
    demos/session_cramped_2026-05-05.parquet
```

The parquet schema matches what `src/training/bc.py:load_demos_to_dataset`
expects, with `source="human_unity"` and `raw_obs=None` (Unity does not
currently emit raw feature vectors -- BC training from Unity demos is
deferred until that channel is wired up).

### 2. Replay through Carroll and diff

```bash
python scripts/verify_unity_parity.py \
    --jsonl demos/session_cramped_2026-05-05.jsonl \
    --layout cramped_room \
    --report runs/parity_report.md
```

The script:

1. Loads the JSONL and groups records into per-episode action
   sequences.
2. Replays each episode through Carroll's `OvercookedEnv`, translating
   GRACE action indices to Carroll indices (the action permutation
   between the two enums is documented in `src/envs/unity_parity.py`;
   only `INTERACT` shares an index).
3. Diffs Carroll's post-tick `state_text` against Unity's, step by
   step, using `difflib.unified_diff`.
4. Writes a markdown report with per-episode and aggregate parity
   rates, the first divergence step, and the first three diff blocks
   per episode for easy debugging.

Exit codes:

| Code | Meaning |
| --- | --- |
| 0 | All episodes had `parity_rate == 1.0` -- PASS |
| 1 | At least one episode diverged -- FAIL |
| 2 | `overcooked_ai_py` is not installed |

## What to do if parity fails

Because Carroll is the ground truth, **fix Unity to match Carroll**, not
the other way round. Common causes:

1. **Action enum drift.** Verify Unity's discrete action handler maps
   `0..5` to STAY/N/S/E/W/INTERACT in that order. The GRACE-to-Carroll
   permutation lives in `src.envs.unity_parity.GRACE_TO_CARROLL`; if
   you change one side you must change the other.
2. **State serializer drift.** `Unity StateSerializer.cs` must produce
   exactly the same string layout as
   `src/envs/python_env.py:_carroll_state_to_text`. Both are pinned to
   `STATE_TEXT_VERSION = "v1"`. Changes require bumping the version on
   *both* sides simultaneously, plus invalidating any prompt-hash
   caches.
3. **Off-by-one tick reporting.** Unity logs the post-tick state; if it
   logs the pre-tick state instead, every line shifts by one step.
4. **Pot dynamics.** Cook time, onion capacity (3), ready/cooking
   transitions -- these must match Carroll's `OvercookedGridworld`
   defaults.
5. **Tile resolve order.** Carroll resolves moves before interactions,
   then advances pots. `ChefSimulation.Tick()` should follow the same
   order.

The unified-diff blocks in the parity report point directly at which
field went wrong (agent position, held item, pot count, cook time, etc.).

## Known limitations

- `state_text` format must match exactly between Unity's
  `StateSerializer.cs` and Python's `src/envs/state_text.py` /
  `src/envs/python_env.py:_carroll_state_to_text`. Both pinned to
  `STATE_TEXT_VERSION = "v1"`. A whitespace change on either side
  silently corrupts every parity check.
- `raw_obs` is not emitted by Unity yet, so the parquet output cannot
  feed BC training without re-deriving observations. Adding that
  channel is left for a follow-up phase (it is independent of parity).
- The verifier compares state strings, not raw simulator structs.
  String parity is a strict superset (if every visible field matches,
  invisible fields cannot differ on a deterministic sim) -- but a
  buggy serializer that hides differences would let parity report PASS
  while real states diverge. Mitigated by serializing every
  state-bearing field (positions, held items, all pot fields, score).
- Action 5 (INTERACT) is the only fixed point between GRACE and
  Carroll's action enums. The other five are permuted: see
  `src/envs/unity_parity.py:GRACE_TO_CARROLL` for the mapping.
