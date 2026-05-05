# `Scripts/ML/` — Dormant in Unity 6

This folder is the original Phase 6 ML-Agents scaffold. It is **inactive** in
the current Unity 6 (`6000.4.5f1`) editor: ML-Agents 3.0 still references the
old `Unity.Sentis` namespace which no longer exists in Unity 6.

The `Grace.Unity.ML` and `Grace.Unity.Recording` asmdefs gate compilation
behind a `GRACE_HAS_MLAGENTS` define that is auto-set only when the
`com.unity.ml-agents` package is present. Without that package the assemblies
silently compile out — none of the `.cs` files in this folder are part of the
shipped game.

Why we keep it instead of deleting:
- If ML-Agents publishes a Unity 6-compatible release, dropping the package
  back into `Packages/manifest.json` re-activates this code immediately.
- The Side Channel `StateSerializer` and 6-action `ChefAgent` are reference
  implementations the Python research-side wrapper (`src/envs/unity_env.py`)
  matches against.

Per `GAME_DESIGN.md` row 13's note, RL training currently happens on the
Python side (Carroll's overcooked-ai); Unity is the playable game and
visualization layer until the ML-Agents Unity 6 gap closes.

If you are reading code in `Assets/Scripts/`, you can ignore everything in
this folder — it has no runtime effect on the current game.
