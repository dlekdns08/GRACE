# `unity_env/` — GRACE Unity project (3D Overcooked-clone)

This directory hosts the **playable 3D Overcooked-style game** described in
`unity_env/GAME_DESIGN.md`. Phase G1 (this commit) introduces a pure-C# core
simulation under `Assets/Scripts/Core/` that is the single source of truth
for game state; the existing ML-Agents code, the upcoming render layer, and
the Network/NGO multiplayer layer all consume it identically.

For research-side parity with Carroll's Overcooked-AI, see `DESIGN.md`
sections 3.1 and 4.1.

## Game architecture (Phase G1+)

```
Assets/Scripts/
├── Core/                ← pure C#, no UnityEngine deps; deterministic
│   ├── KitchenLayout.cs       ← parsed grid (TileKind, GridPos)
│   ├── LayoutLoader.cs        ← Carroll ASCII parser
│   ├── PotState.cs            ← pot state machine (3 onions, 20-tick cook)
│   └── ChefSimulation.cs      ← Carroll-faithful simulation core
├── ML/                  ← ML-Agents binding (existing path, refactored)
│   ├── ChefAgent.cs           ← Agent; delegates to ChefSimulation
│   ├── KitchenEnvironment.cs  ← thin MB wrapper around ChefSimulation
│   ├── PotController.cs       ← visual mirror of PotState
│   ├── PlayerInput.cs / HumanPlayDriver.cs / KitchenHUD.cs
│   ├── StateSerializer.cs / KitchenSideChannelHook.cs
└── Recording/
    └── TrajectoryRecorder.cs  ← JSONL (one line per agent per tick)

Assets/Resources/Layouts/
├── cramped_room.txt
├── asymmetric_advantages.txt
├── coordination_ring.txt
└── forced_coordination.txt    ← all four are Carroll's standard layouts

Tests/EditMode/
├── LayoutLoaderTests.cs
├── PotStateTests.cs
└── ChefSimulationTests.cs
```

The `Core/` simulation is consumed by three independent layers:

```
                  ┌──────────────────────┐
                  │ Core.ChefSimulation  │  pure C#, deterministic
                  └──────────┬───────────┘
                             │
            ┌────────────────┼────────────────┐
            │                │                │
       Render/+Input      Network/        ML/ (this folder)
       (Phase G2/G3)      (NGO host-auth) (ML-Agents Academy)
```

The action enum is **6 values** (Carroll-faithful):

| id | name | meaning |
|----|------|---------|
| 0 | STAY | do nothing |
| 1 | N | move north (y decreases; y=0 is top of layout) |
| 2 | S | move south |
| 3 | E | move east |
| 4 | W | move west |
| 5 | INTERACT | pick up / drop / cook / serve, depending on facing tile |

See `unity_env/GAME_DESIGN.md` for full design lock-ins.

## Phase 6 stub note (historical)

Originally this directory was a Phase 6 stub: the C# scripts compiled against
a standard ML-Agents install but did not ship art, prefabs, scenes, or
training configs. Phase G1 keeps that ML-Agents path alive (now under
`Scripts/ML/`) but rebuilt on top of the deterministic `Core/` simulation.

## Requirements

- **Unity 2022.3 LTS** (any patch revision).
- **ML-Agents 2.x** Unity package (Release 20 or later). Install via the
  Package Manager: `com.unity.ml-agents` (and optionally `com.unity.ml-agents.extensions`).
- A working `mlagents` Python install on the host driving training (added by a
  later phase to the GRACE Python deps).

## Setup

1. Create a fresh Unity 2022.3 project (3D — URP or built-in both work).
2. Open the Package Manager and install `com.unity.ml-agents`.
3. Copy the contents of `Assets/Scripts/` from this directory into the new
   project's `Assets/Scripts/`. The scripts share the namespace `GRACE.Unity`
   and have no asset dependencies.
4. Build a scene:
   - Create an empty `KitchenManager` GameObject and attach
     `KitchenEnvironment` and `KitchenSideChannelHook`.
   - Spawn N `ChefAgent` GameObjects (each needs a `Behavior Parameters`
     component, a `Decision Requester`, and a discrete action space of size 7).
     Drag them into `KitchenEnvironment.Agents`. Set each agent's
     `AgentName` (e.g. `agent_0`, `agent_1`).
   - Spawn M `PotController` GameObjects and drag them into
     `KitchenEnvironment.Pots`. Position each pot so its local x/z grid
     coordinates match a kitchen counter cell.
   - Set `LayoutWidth` / `LayoutHeight` on `KitchenEnvironment` if not 5x5.
5. (Optional) Build the scene to a standalone player so the Python wrapper can
   spawn it head-less.

## Side-channel contract

`StateSerializer` ships a textual rendering of the kitchen (matching v1 of
`src/envs/state_text.py`) over a side channel with GUID

```
621f0a70-4f87-11ea-a6bf-784f4387d1f7
```

The Python wrapper at `src/envs/unity_env.py` (later phase) must register a
matching side channel with the **same GUID** and decode the UTF-8 string
payloads. Bumping `StateSerializer.FormatVersion` is a breaking change and
must be mirrored on the Python side.

## Human-Play Mode (Phase 9)

For two-player local co-op (no ML-Agents Python runtime required), the
scaffold ships four extra C# scripts:

| Script | Role |
|---|---|
| `PlayerInput.cs` | Maps keyboard scheme (WASD or arrows) to the 7-discrete-action space. |
| `HumanPlayDriver.cs` | Fixed-rate tick loop (default 8 Hz) that calls `ChefAgent.ApplyAction` directly, bypassing the ML-Agents Academy. |
| `KitchenHUD.cs` | TextMeshPro HUD: step / score / soups served / per-agent held item / pot status. |
| `TrajectoryRecorder.cs` | Append-only JSONL writer (one line per agent per tick) for behaviour-cloning datasets. |

### Quick start

1. Build the scene `Assets/Scenes/CrampedRoom_Play.unity` by following
   `Assets/Scenes/CrampedRoom_Play.unity.MANUAL.md` (~15 min).
2. Press **Play**.
   - Player 1: `W` `A` `S` `D` + `Space` (pickup/drop) + `E` (interact).
   - Player 2: arrow keys + `Right Shift` (pickup/drop) + `Right Ctrl` (interact).
3. Episodes end on `MaxSteps=400` or 5 soups served (whichever first); the
   driver auto-resets and the JSONL recorder bumps `episode` to keep
   appending.

### Recording demonstrations

`TrajectoryRecorder` writes one JSONL line per (agent, tick) to
`Assets/_demos/play_session.jsonl` by default. Schema:

```json
{"episode": 0, "step": 12, "agent_id": "agent_0", "action": 4, "reward": 0.000, "done": false, "state_text": "Step: 12/400\\nScore: 0 (soups served: 0)\\n..."}
```

To convert to parquet for downstream BC training, the Python half of
the project (Phase 9) provides `scripts/jsonl_to_parquet.py`. As a
one-liner you can also do:

```python
import pandas as pd
pd.read_json("Assets/_demos/play_session.jsonl", lines=True).to_parquet("demos.parquet")
```

### Mode switching

`HumanPlayDriver.humanMode = false` makes the driver a no-op; the scene
falls back to standard ML-Agents behaviour (Academy steps each
`ChefAgent` via `OnActionReceived`). Both code paths now route through
the same `ChefAgent.ApplyAction(int)` so simulator behaviour is
identical between human play and trained-policy play.

### Play-vs-trained-policy

Out of scope for this phase — see the **TODO** section at the bottom of
`CrampedRoom_Play.unity.MANUAL.md` for the rough recipe (export `.onnx`,
swap one agent's `BehaviorType` to `InferenceOnly`, drop it from
`HumanPlayDriver.players`).

## Notes / caveats

- These scripts are a *scaffold*. They compile against the standard
  ML-Agents API surface but were not tested inside a Unity Editor in this
  phase — expect to wire up `Behavior Parameters`, `DecisionRequester`, and
  action / observation sizes by hand.
- `StateSerializer.SendKitchen` is provided but not auto-invoked from a
  per-tick hook. The intended call site is right after
  `KitchenEnvironment.Tick()`; a future phase will wire this into the
  `Academy.Instance.OnEnvironmentReset` / `DecisionRequester` flow.
- Phase 1 / Phase 2 (running in parallel) own everything under `src/` — do
  not edit Python files from this directory.
