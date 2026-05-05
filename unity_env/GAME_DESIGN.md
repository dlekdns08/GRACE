# GRACE Unity Game Design Doc

> Design decisions for the playable 3D Overcooked-style game. **This is the contract.** If anything below changes, update *this doc* before changing code.

## 1. Vision

A real, playable 3D cooperative cooking game (Overcooked-clone) that:
- **Plays well**: smooth controls, good visual feedback, online + local co-op
- **Stays research-faithful**: every game state is bit-identical to Carroll's overcooked-ai so demonstrations and BC checkpoints are interoperable
- **Ships**: builds for Mac, Windows, and WebGL (browser play via shareable link)

## 2. Decisions (locked)

| # | Topic | Decision |
|---|---|---|
| 1 | View | **3D, low-poly**, top-down 30° tilted camera (semi-isometric look) |
| 2 | Movement | **Hybrid**: internal grid state (Carroll-faithful) + visual smooth interpolation (~150ms lerp) |
| 3 | Faithfulness | **Carroll 100%**: same 6-action enum (N, S, E, W, STAY, INTERACT), same reward (+20/serve), same layouts |
| 4 | Assets | **CC0 free**: [Kenney 3D](https://kenney.nl/assets/category:3d) (Furniture Kit, Food Kit, Modular Kitchen, Mini Characters) + [Quaternius](https://quaternius.com/) (Modular Characters) |
| 5 | Platforms | **Desktop (Mac/Win) + WebGL** |
| 6 | Multiplayer | **Netcode for GameObjects (NGO) + Unity Relay** (UGS). 2 players co-op (room for 4 in code). Free tier: 100 CCU. |
| 7 | Render pipeline | **URP** (Universal Render Pipeline) — WebGL-compatible, mobile-friendly |
| 8 | Unity version | **2022.3 LTS** (matches existing scaffold) |
| 9 | Input | **Unity Input System** (new). Keyboard, Gamepad (Xbox/PS), Touch (mobile-future) |
| 10 | Audio | **Unity built-in audio** + Kenney free SFX/music packs |
| 11 | Networking model | **Host-Authoritative** (one player hosts; others connect via Relay code). Lockstep state sync at 8 Hz tick rate. |
| 12 | Tick rate | **8 Hz simulation tick** (matches existing `HumanPlayDriver.ticksPerSecond=8`); **60 FPS rendering** with interpolation |
| 13 | Action enum | `0=STAY, 1=N, 2=S, 3=E, 4=W, 5=INTERACT` — exact match with Carroll's action indices |

### Side notes

- Existing `ChefAgent.cs` uses 7 actions (with separate pickup/drop). **Phase G1 will collapse this to 6** by merging pickup/drop into `INTERACT` — Carroll behavior. This is breaking — Phase 9 demos collected with the 7-action scheme will be invalidated. Mitigated by clean re-record after G1.
- Online multiplayer in WebGL is non-trivial: NGO uses Unity Transport (UTP) which supports WebRTC for WebGL via Unity Relay. **No separate relay server required.**
- **ML-Agents disabled in Unity 6** (Editor 6000.4.5f1). ML-Agents 3.0 still references the old `Unity.Sentis` namespace, but Unity 6 ships only the new `Unity.InferenceEngine` shim (Sentis → InferenceEngine rename). To keep the game compiling, the `com.unity.ml-agents` package is **removed from `Packages/manifest.json`** and the `Grace.Unity.ML` + `Grace.Unity.Recording` asmdefs are gated behind `GRACE_HAS_MLAGENTS` via `versionDefines` — they auto-activate if the package returns. RL training continues on the Python side (Carroll's overcooked-ai) — Unity is the **game/visualization layer only** until ML-Agents adds Unity 6 support. To re-enable: downgrade to Unity 2023.2 LTS or wait for ML-Agents to publish a Unity 6-compatible release.

## 3. Scope (what's in / out)

### In
- 4 layouts: `cramped_room`, `asymmetric_advantages`, `coordination_ring`, `forced_coordination` (Carroll's standard set)
- Title menu + Layout selector + Mode selector (Solo vs AI / Local Co-op / Online Co-op)
- Pause menu + Round end summary
- Online lobby: Host creates a Relay code, Guest types code
- Trajectory recorder (per-step JSONL → parquet)
- Audio: footstep / pickup / drop / interact / serve / round end + 1 BGM track
- Particles: pot steam, pot ready glow, serve confetti
- WebGL build hosted on GitHub Pages

### Out (explicitly deferred)
- Random level generation
- Time-of-day or weather variations
- Steam Workshop / mod support
- 4-player play (code is room-of-4 capable but UI/level only show 2 players)
- Mobile touch UI (codepath exists; not first-class)
- Voice chat
- Player avatars / cosmetics
- Persistent stats / leaderboard

## 4. Architecture

```
unity_env/
├── Assets/
│   ├── Scenes/
│   │   ├── 00_Title.unity
│   │   ├── 01_Lobby.unity           ← layout select + Relay code lobby
│   │   ├── 02_GameRoom.unity        ← main gameplay scene
│   │   └── 03_RoundEnd.unity
│   ├── Scripts/
│   │   ├── Core/                    ← Phase G1 (game logic, no Unity deps where possible)
│   │   │   ├── KitchenLayout.cs
│   │   │   ├── LayoutLoader.cs
│   │   │   ├── Tile.cs
│   │   │   ├── PotState.cs
│   │   │   ├── ChefSimulation.cs    ← pure C# state machine
│   │   │   └── GameTick.cs
│   │   ├── Render/                  ← Phase G2/G3 (visuals)
│   │   │   ├── ChefVisual.cs
│   │   │   ├── PotVisual.cs
│   │   │   ├── KitchenRenderer.cs
│   │   │   ├── MovementInterpolator.cs
│   │   │   └── CameraRig.cs
│   │   ├── Input/                   ← Unity Input System
│   │   │   ├── PlayerInputController.cs
│   │   │   └── ChefControls.inputactions
│   │   ├── Network/                 ← NGO layer
│   │   │   ├── NetworkChefAgent.cs
│   │   │   ├── NetworkKitchen.cs
│   │   │   ├── LobbyManager.cs
│   │   │   └── RelayBootstrap.cs
│   │   ├── UI/                      ← menus
│   │   │   ├── TitleMenu.cs
│   │   │   ├── LayoutSelector.cs
│   │   │   ├── HUD.cs
│   │   │   └── RoundEndScreen.cs
│   │   ├── Audio/
│   │   │   └── AudioMaster.cs
│   │   ├── Recording/
│   │   │   └── TrajectoryRecorder.cs    ← already exists, may need 6-action update
│   │   └── ML/                      ← existing ML-Agents path (kept)
│   │       ├── ChefAgent.cs
│   │       ├── KitchenEnvironment.cs
│   │       └── StateSerializer.cs
│   ├── Resources/
│   │   ├── Layouts/
│   │   │   ├── cramped_room.txt
│   │   │   ├── asymmetric_advantages.txt
│   │   │   ├── coordination_ring.txt
│   │   │   └── forced_coordination.txt
│   │   └── Audio/
│   ├── Prefabs/
│   ├── Materials/
│   └── Sprites/
├── ProjectSettings/
└── Tests/
    ├── EditMode/
    └── PlayMode/
```

### Two execution paths share `Core/`

```
                    ┌──────────────────────┐
                    │ Core/ChefSimulation  │  pure C#, deterministic, no Unity deps
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
        ┌─────▼─────┐    ┌─────▼─────┐    ┌────▼─────┐
        │ Render/   │    │ Network/  │    │ ML/      │
        │ + Input   │    │ NGO sync  │    │ MLAgents │
        └───────────┘    └───────────┘    └──────────┘
        Local play       Online play       Training
```

Same simulation core → all three modes produce identical state evolutions. Carroll's Python is checked against `ChefSimulation` for parity.

## 5. Networking model

### Topology
- **Host-authoritative**: one client runs the simulation tick and broadcasts state. Guests submit input intents; host applies them.
- 2-player default; code accepts up to 4.
- 8 Hz tick → ~125 ms per tick. With Relay round-trip ~80-150 ms, perceived lag is one-tick-worth (acceptable for a 8 Hz game).

### Connection flow
1. Host clicks "Create Room" → NGO + Relay allocates a `joinCode` (6 chars).
2. Host shares `joinCode` (Discord, etc.).
3. Guest types `joinCode` in the join field → connects via Relay.
4. Both load the game scene → host spawns kitchen, both spawn chefs.
5. Each tick: every client polls input → sends `ServerRpc(intent)` → host writes intent to per-player slot → host runs `ChefSimulation.Tick()` → state replicated via `NetworkVariable<KitchenState>`.

### Authority
- Host: simulation, reward computation, episode termination
- Guests: only input (no client-side prediction in v1; can add later if needed)
- Reconnection: not in v1; if guest disconnects, host pauses

## 6. Asset list (CC0)

| Asset | Source | Purpose |
|---|---|---|
| Kenney Furniture Kit | https://kenney.nl/assets/furniture-kit | Tables, counters |
| Kenney Food Kit | https://kenney.nl/assets/food-kit | Onion, dish, soup-bowl, etc. |
| Kenney Modular Kitchen | https://kenney.nl/assets/modular-buildings | Walls, floor tiles |
| Quaternius Modular Characters | https://quaternius.com/packs/modularcharacters.html | Chef bodies + outfits |
| Kenney Audio Pack | https://kenney.nl/assets/category:Audio | All SFX |
| Kenney Game Icons | https://kenney.nl/assets/game-icons | UI buttons |

Asset import guide: see `unity_env/ASSET_IMPORT.md` (Phase G2).

## 7. Acceptance criteria per phase

| Phase | "Done" means |
|---|---|
| G1 | `cramped_room` layout, gray-box visuals, two human players (single keyboard) can deliver soups; Unity Edit-mode tests pass |
| G6 | Same layout + same action sequence → Carroll Python and Unity produce identical (state, reward) trace |
| G3 | 30s GIF looks like a real game (animations, sound, particles) |
| Network | Two laptops connect via Relay code, play one round to completion |
| G5 | `Builds/macos/grace.app` runs; `Builds/webgl/index.html` runs in browser; both to-completion |

## 8. Open questions (to revisit)

- **Color palette / visual style**: low-poly is decided; specific palette TBD until G2 (defer to art pass)
- **Music**: 1 BGM loop; pick one Kenney track later
- **Round timer**: Carroll uses fixed-step horizon (default 400 steps = 50 sec at 8 Hz). Game UI will show seconds remaining. If we want tension, add a "speed up at end" visual cue (G3).
- **AI partner balance**: when Solo vs AI mode plays a learned PPO checkpoint, the difficulty depends on training quality. Add a "policy strength" toggle?

## 9. Out of repo

Things hosted elsewhere (not committed):
- Built `.app` / `.exe` artifacts (use GitHub Releases or itch.io)
- WebGL build hosting (GitHub Pages from `/docs`, or itch.io)
- Unity Cloud Project ID + Relay credentials (in `ProjectSettings/UnityServicesProjectConfiguration.json` — this WILL be committed once user creates the project; nothing secret in it)
