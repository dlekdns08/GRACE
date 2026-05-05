# `unity_env/` — Unity ML-Agents scaffold (GRACE Phase 6)

This directory holds a **stub Unity project** for the Overcooked-style
environment described in `DESIGN.md` section 4.1. It is intentionally minimal:
the C# scripts compile against a standard ML-Agents install but do not yet
ship art, prefabs, scenes, or training configs. Future phases will flesh those
out. The Python side wrapper that talks to this build will live at
`src/envs/unity_env.py` (added in a later phase).

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
