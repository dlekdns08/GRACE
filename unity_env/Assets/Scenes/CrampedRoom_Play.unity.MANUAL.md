# `CrampedRoom_Play.unity` — Manual Scene Setup Guide

This guide reconstructs the **two-player human-play scene** for GRACE
Phase 9 inside the Unity Editor. We can't ship the binary `.unity` asset
from text, so follow the steps below to build it once. Estimated time:
~15 minutes for a Unity-comfortable user.

> Target: **Unity 2022.3 LTS** with **ML-Agents 2.x** and **TextMeshPro**
> (auto-installed in modern Unity; you'll be prompted to import TMP
> Essentials the first time you add a TMP widget).

---

## 0. Prereqs

1. The C# scripts under `Assets/Scripts/` (this directory) compile cleanly.
2. Package Manager has `com.unity.ml-agents` installed.
3. TextMeshPro is available (default in Unity 2022.3).

`[SCREENSHOT: Package Manager — ml-agents installed]`

---

## 1. Create and save the scene

1. **File → New Scene → Basic (Built-in)**.
2. **File → Save As…** → `Assets/Scenes/CrampedRoom_Play.unity`.

`[SCREENSHOT: Project window showing CrampedRoom_Play.unity]`

---

## 2. Kitchen GameObject

1. Hierarchy → right-click → **Create Empty** → name `Kitchen`.
2. With `Kitchen` selected, in the Inspector:
   - **Add Component → KitchenEnvironment**.
     - `Max Steps = 400`
     - `Layout Width = 5`, `Layout Height = 5`
     - `Agents` and `Pots` lists are wired below.

`[SCREENSHOT: Kitchen inspector — KitchenEnvironment component]`

---

## 3. Two ChefAgents

For each agent (`Agent0`, `Agent1`):

1. Hierarchy → right-click `Kitchen` → **Create Empty Child** → name
   `Agent0` (and later `Agent1`).
2. **Add Component → ChefAgent**.
   - `Agent Name = "agent_0"` (and `"agent_1"` for the second).
   - `Kitchen = <drag the Kitchen object>`.
3. **Add Component → Behavior Parameters** (auto-added by ML-Agents'
   `Agent` base class — verify it exists).
   - `Behavior Name = "Chef"` (any string is fine; identical for both is OK).
   - **Behavior Type = `Heuristic Only`**. We don't actually use the
     `Heuristic()` callback in human-play mode (the `HumanPlayDriver`
     bypasses ML-Agents stepping), but `HeuristicOnly` prevents the
     Academy from complaining about a missing trainer.
   - `Vector Observation → Space Size = ` whatever
     `ChefAgent.GetCurrentObservationDim()` returns for your wiring.
     With 2 agents and 1 pot that's `4 + 1*4 + 1*3 + 1 = 12`.
   - `Actions → Discrete Branches = 1`, `Branch 0 Size = 7`.
4. **Add Component → Decision Requester**.
   - `Decision Period = 1`, leave `Take Actions Between Decisions` on.
5. **Add Component → PlayerInput** (this script).
   - `Agent = <drag the ChefAgent on the SAME object>`.
   - `Scheme = WASD` for `Agent0`, `Scheme = Arrows` for `Agent1`.

`[SCREENSHOT: Agent0 inspector — ChefAgent + BehaviorParameters + DecisionRequester + PlayerInput stacked]`

---

## 4. Wire `Kitchen.Agents`

1. Select `Kitchen`.
2. In `KitchenEnvironment`, expand **Agents** and set **Size = 2**.
3. Drag `Agent0` into `Element 0`, `Agent1` into `Element 1`. Order matters
   — `Agent0` is the "first" agent and is the only one that ticks the
   simulation inside `ApplyAction`.

---

## 5. Pot

1. Hierarchy → right-click `Kitchen` → **Create Empty Child** → name `Pot0`.
2. **Add Component → PotController**.
3. Position the pot so it's adjacent to a cell an agent can stand on.
   E.g. `Transform → Position = (2, 0, 2)`.
4. On `Kitchen`, expand **Pots** in `KitchenEnvironment`, set **Size = 1**,
   and drag `Pot0` into `Element 0`.

`[SCREENSHOT: Kitchen with Agent0/Agent1/Pot0 children]`

---

## 6. HUD Canvas

1. Hierarchy → right-click → **UI → Canvas** (auto-creates `EventSystem`
   too — keep it).
2. Inside the Canvas, create six `UI → Text - TextMeshPro` widgets and
   name them:
   - `StepText`
   - `ScoreText`
   - `SoupsText`
   - `Agent0HeldText`
   - `Agent1HeldText`
   - `PotStatusText`

   The first time you add a TMP widget Unity will prompt you to import
   **TMP Essentials** — accept.
3. Lay them out vertically in the top-left corner. A `VerticalLayoutGroup`
   on a parent panel makes this trivial.
4. On the Canvas (or any sibling object), **Add Component → KitchenHUD**.
   - `Kitchen = <drag Kitchen>`.
   - Drag each TMP widget into the matching field (`stepText`, ...).

`[SCREENSHOT: Canvas hierarchy with six TMP widgets]`
`[SCREENSHOT: KitchenHUD inspector with all refs assigned]`

---

## 7. Driver

1. Hierarchy → right-click → **Create Empty** → name `Driver`.
2. **Add Component → HumanPlayDriver**.
   - `Human Mode = true`
   - `Ticks Per Second = 8`
   - `Kitchen = <drag Kitchen>`
   - `Players` list, **Size = 2**:
     - `Element 0 = <drag Agent0's PlayerInput>`
     - `Element 1 = <drag Agent1's PlayerInput>`
   - `Hud = <drag the KitchenHUD>` (optional; HUD also self-refreshes on LateUpdate).
3. **Add Component → KitchenSideChannelHook**.
   - Leave `Serializer` null — it auto-creates one.
   - `Kitchen = <drag Kitchen>` (used by future tick-driven `SendKitchen` calls).

`[SCREENSHOT: Driver inspector with HumanPlayDriver + KitchenSideChannelHook]`

---

## 8. Trajectory Recorder (optional but recommended for BC)

1. Hierarchy → right-click → **Create Empty** → name `Recorder`.
2. **Add Component → TrajectoryRecorder**.
   - `Kitchen = <drag Kitchen>`
   - `Serializer = <drag the StateSerializer asset>` — wait, the
     `StateSerializer` is **not** a MonoBehaviour, it's allocated at
     runtime by `KitchenSideChannelHook`. Leave this field null and
     instead either:
     (a) edit `KitchenSideChannelHook` to expose its `Serializer`
     publicly (already public), and drag the *Driver* GameObject; the
     inspector will let you pick the `StateSerializer` reference once
     it's set in Awake — easiest is to assign in code via a small wiring
     script, OR
     (b) just leave it null and accept that `state_text` will be empty
     in JSONL; you can post-process by replaying the action sequence in
     Python.
   - `Output Path = Assets/_demos/play_session.jsonl`
   - `Recording = true`
3. Wire the recorder into the driver: select `Driver`, drag the
   `Recorder` GameObject into `HumanPlayDriver.recorder`.

`[SCREENSHOT: Recorder inspector + Driver inspector with recorder wired]`

---

## 9. Final hierarchy check

```
CrampedRoom_Play
├─ Kitchen
│  ├─ Agent0   (ChefAgent + BehaviorParameters + DecisionRequester + PlayerInput[WASD])
│  ├─ Agent1   (ChefAgent + BehaviorParameters + DecisionRequester + PlayerInput[Arrows])
│  └─ Pot0     (PotController)
├─ Canvas
│  ├─ StepText / ScoreText / SoupsText
│  ├─ Agent0HeldText / Agent1HeldText / PotStatusText
│  └─ (KitchenHUD on Canvas)
├─ EventSystem
├─ Driver      (HumanPlayDriver + KitchenSideChannelHook)
└─ Recorder    (TrajectoryRecorder)
```

`[SCREENSHOT: full scene hierarchy]`

---

## 10. Press Play

1. Hit **Play**.
2. Player 1: `W` `A` `S` `D` to move, `Space` to pickup/drop, `E` to
   interact (place onion in pot adjacent to you, etc).
3. Player 2: arrow keys to move, `Right Shift` to pickup/drop,
   `Right Ctrl` to interact.
4. The HUD updates 8 times per second; pot cooks for 20 ticks once full.
5. Episode auto-resets after 5 soups served or 400 steps.

If recording is on, `Assets/_demos/play_session.jsonl` will grow as you
play. Convert to parquet on the Python side (TODO: see
`unity_env/README.md → Human-Play Mode`).

---

## TODO: Play vs. trained policy

Loading an exported `.onnx` policy and binding it to one `ChefAgent`
while the other is human-controlled is feasible but requires:

1. Training a policy on the Python side and exporting via
   `mlagents-learn ... --resume --inference` to produce a `.onnx`.
2. On `Agent0` (or `Agent1`), set `BehaviorParameters → Behavior Type =
   InferenceOnly` and drag the `.onnx` into `Model`.
3. Remove that agent's `PlayerInput` from `HumanPlayDriver.players` so
   the driver doesn't override its action.
4. Let the Academy step that agent normally; the human player still
   ticks via `HumanPlayDriver`.

This is non-trivial because `HumanPlayDriver` currently calls
`ChefAgent.ApplyAction` directly, while ML-Agents inference goes through
`OnActionReceived`. Both call the same logic, but timing/phase has to
be reconciled. Defer until needed.
