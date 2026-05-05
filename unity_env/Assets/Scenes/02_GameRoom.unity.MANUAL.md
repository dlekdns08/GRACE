# 02_GameRoom.unity — Manual Build Guide

> Estimated build time: **20 min** (assuming `Assets/Prefabs/` has been populated per `ASSET_IMPORT.md`).
> Main gameplay scene. Loads a Carroll layout, spawns chefs, runs sim, displays HUD.

## Prerequisites

- All scripts compile.
- Tile prefabs created in `Assets/Prefabs/Tiles/` (per `ASSET_IMPORT.md`).
- `ChefPrefab.prefab` created (see ASSET_IMPORT.md §7).
- A Universal Render Pipeline asset exists at `Assets/Settings/URP-HighFidelity.asset` and is assigned in **Edit → Project Settings → Graphics → Scriptable Render Pipeline Settings**.

## Steps

### 1. Create scene

`[INSPECTOR]` Right-click `Assets/Scenes` → **Create → Scene** → `02_GameRoom`. Open it.

### 2. Lighting

`[INSPECTOR]` Keep the default `Directional Light`. Rotate it to `(50, -30, 0)` for nicer top-down shading.

### 3. Camera rig

`[INSPECTOR]`
1. **GameObject → Camera** → name `GameCamera`. Tag `MainCamera`.
2. Add component **Grace.Unity.Render.CameraRig** (auto-adds `Camera`).
3. Camera settings:
   - **Projection**: `Perspective`, **Field of View**: `35`
   - **Clipping Planes**: Near `0.3`, Far `200`
4. CameraRig fields:
   - `Tilt = 30`
   - `MinDistance = 8`
   - `DistancePerTile = 1.4`
   - Leave `Kitchen` empty for now; `CameraRig.Start()` finds it.

### 4. Kitchen

`[INSPECTOR]`
1. **GameObject → Create Empty** → name `Kitchen`.
2. Add **Grace.Unity.Render.KitchenRenderer** component.
3. Drag prefabs from `Assets/Prefabs/Tiles/` into:
   - `FloorPrefab`, `CounterPrefab`, `WallPrefab`,
   - `OnionDispenserPrefab`, `DishDispenserPrefab`,
   - `PotPrefab`, `ServingCounterPrefab`.
4. `LayoutName = cramped_room` (or empty to read from `GameModeFlags.SelectedLayout`).
5. Drag `Kitchen` GameObject into `GameCamera.CameraRig.Kitchen`.

> If you want the layout to follow the title-screen selection: change `KitchenRenderer.Start()` later, or do it from a small bootstrap script. For now, hard-code per scene.

### 5. NetworkManager (online mode only)

`[INSPECTOR]` If coming from `01_Lobby` via `DontDestroyOnLoad`, the `NetworkManager` already exists. If you opened this scene directly (testing offline), skip this section.

### 6. NetworkKitchen

`[INSPECTOR]`
1. **GameObject → Create Empty** → name `NetworkKitchen`.
2. Add components:
   - `NetworkObject` (Netcode)
   - `Grace.Unity.Network.NetworkKitchen`
3. Drag `NetworkKitchen` into the prefab folder if you want it spawnable. Otherwise it lives in-scene.
4. `NetworkKitchen.LayoutName = cramped_room` (or wire to GameModeFlags later).

### 7. Player spawner

`[INSPECTOR]`
1. **GameObject → Create Empty** → name `PlayerSpawner`.
2. Add **Grace.Unity.Network.NetworkPlayerSpawner**.
3. Drag `Assets/Prefabs/ChefPrefab.prefab` into `NetworkChefPrefab` (the prefab must have `NetworkObject` + `NetworkChefAgent` + `ChefVisual` + `MovementInterpolator`).

### 8. HUD

`[INSPECTOR]`
1. **GameObject → UI → Canvas** → name `HUDCanvas`. Reference resolution `1920×1080`.
2. **GameObject → UI → Event System** (if not already present from prior scene).
3. Inside `HUDCanvas`, add 6 TMP Text fields:
   - `TimerText` (top-center, large)
   - `ScoreText` (top-left)
   - `SoupsText` (top-left, below score)
   - `Player1HeldText` (bottom-left)
   - `Player2HeldText` (bottom-right)
   - `PotsText` (top-right)
4. Add **Grace.Unity.UI.HUD** to `HUDCanvas`.
5. Wire:
   - `Kitchen` → drag the in-scene `NetworkKitchen` GameObject (online).
   - or `OfflineSim` → leave empty unless you have a script that constructs a local `ChefSimulation` at runtime and writes the reference into the HUD.
6. Wire each TMP Text into the corresponding HUD slot.
7. `TicksPerSecond = 8`.

### 9. AudioMaster

`[INSPECTOR]`
1. **GameObject → Create Empty** → name `AudioMaster`. Add **Grace.Unity.Audio.AudioMaster**.
2. In `Entries`, add one element per `SfxId` and drop the corresponding clip(s) imported via `ASSET_IMPORT.md`.
3. (Optional) Drop a BGM AudioSource into `Music`.

### 10. Particles (optional polish)

`[INSPECTOR]` Inside the Pot prefab, you can attach a steam `ParticleSystem` and a `ReadyGlow` child GameObject. The `PotVisual` component (added on the Pot prefab) wires them up and toggles them based on state.

### 11. Save + Build Settings

`Ctrl/Cmd-S`. **File → Build Settings → Add Open Scenes**. Should be index 2.

## Done when

- [ ] Entering Play Mode → kitchen tiles appear in a 30°-tilted view.
- [ ] HUD timer counts down from 50.0s.
- [ ] In Solo vs AI / Local Co-op, pressing WASD moves a chef one tile per ~150 ms; pressing Space picks up onions and serves soups.
- [ ] In Online Co-op, both clients see the same kitchen and chef positions update at 8 Hz.
- [ ] No Console errors.

## Notes

- Online vs offline mode selection is read from `GameModeFlags` set by the `00_Title` buttons.
- Prefab names are fixed by `KitchenRenderer.PrefabFor` switch; the **slot** matters, not the prefab's filename.
- The Kitchen GameObject's transform is the origin — keep it at `(0, 0, 0)` so `CameraRig` math works.
