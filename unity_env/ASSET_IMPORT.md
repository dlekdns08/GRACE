# Asset Import Guide

This is the step-by-step for populating `unity_env/Assets/Art/` and `unity_env/Assets/Audio/` with the free CC0 packs locked in `GAME_DESIGN.md` row 4. Do this **before** building scenes from the `*.unity.MANUAL.md` guides.

> All assets are CC0 and re-distributable, but we do **not** commit them to this repo (would bloat the git history). Each developer downloads them locally on first checkout.

## 1. Download

| Pack | URL | Approx. size |
| --- | --- | --- |
| Kenney Furniture Kit | https://kenney.nl/assets/furniture-kit | ~10 MB (.zip, FBX/OBJ) |
| Kenney Food Kit | https://kenney.nl/assets/food-kit | ~12 MB |
| Kenney Modular Buildings (kitchen-style walls + floors) | https://kenney.nl/assets/modular-buildings | ~25 MB |
| Quaternius Modular Characters | https://quaternius.com/packs/modularcharacters.html | ~30 MB |
| Kenney Audio Pack ("RPG Audio" or "Sci-Fi Sounds") | https://kenney.nl/assets/category:Audio | ~5 MB per pack |
| Kenney Game Icons | https://kenney.nl/assets/game-icons | ~3 MB (UI buttons) |

## 2. Extract into project

```
unity_env/Assets/
├── Art/
│   ├── Kenney/
│   │   ├── Furniture/        ← Furniture Kit FBX + textures
│   │   ├── Food/             ← Food Kit FBX + textures
│   │   ├── Modular/          ← Modular Buildings walls/floors
│   │   └── Icons/            ← Game Icons PNGs
│   └── Quaternius/
│       └── Characters/       ← Modular Characters FBX + textures
└── Audio/
    ├── SFX/                  ← extracted .wav / .ogg from Kenney audio packs
    └── BGM/                  ← one music loop, your choice
```

After dropping in the FBX/PNG/WAV files, return to Unity. The Editor will import them; this can take 1–3 min the first time.

## 3. Render pipeline (URP)

1. **Edit → Project Settings → Graphics → Scriptable Render Pipeline Settings** → assign `Assets/Settings/URP-HighFidelity.asset` (created on first URP install).
2. If imported FBX models look pink:
   - Select all model assets, Inspector → **Materials → Extract Materials...** into `Assets/Art/.../Materials/`.
   - Materials use Built-in shaders → run **Window → Rendering → Render Pipeline Converter → Convert Built-in Materials to URP**.

## 4. Lighting (one-time bake)

For the `02_GameRoom` scene:
1. **Window → Rendering → Lighting**.
2. **Mixed Lighting**: enable.
3. **Lightmapping Settings**: keep defaults for v1 (Progressive GPU, indirect res 2).
4. Click **Generate Lighting**. Bakes can take 30 s to 5 min depending on GPU.

(For WebGL, prefer fully baked light or unlit shaders to keep build size down. Iterate later.)

## 5. Tile prefabs

In `Assets/Prefabs/Tiles/`, create one prefab per tile kind (drag a model from the Furniture/Modular/Food packs into an empty scene, scale to **1×1×1 tile**, then drag it into the Project window):

| Prefab name | Source asset (suggestion) |
| --- | --- |
| `FloorPrefab.prefab`           | Modular Buildings → `floor_wood.fbx` (any 1×1 tile) |
| `CounterPrefab.prefab`         | Furniture Kit → `kitchenCabinet.fbx` |
| `WallPrefab.prefab`            | Modular Buildings → `wall_default.fbx` |
| `OnionDispenserPrefab.prefab`  | Food Kit → `onion.fbx` on a small base |
| `DishDispenserPrefab.prefab`   | Food Kit → `plateRound.fbx` on a small base |
| `PotPrefab.prefab`             | Furniture Kit → `kitchenPot.fbx` (or any pot model) |
| `ServingCounterPrefab.prefab`  | Furniture Kit → `kitchenCabinet.fbx` with arrow icon overlay |

Each prefab's **transform pivot must be at the bottom-center of the tile** (Y=0 plane). The KitchenRenderer instantiates them at `(x, 0, -y)`.

### Pot prefab — extra steps

The pot is the most complex prefab:
1. Inside the prefab, add three child empty GameObjects: `Onion1`, `Onion2`, `Onion3`. Place little onion meshes (Food Kit `onion.fbx`) at slight Y offsets to look stacked.
2. Add a child `ParticleSystem` named `SteamParticles` (small puffy white particles, looping but **stopped on Awake**).
3. Add a child `GameObject` named `ReadyGlow` (e.g., a soft halo/sprite), disabled by default.
4. Add component **Grace.Unity.Render.PotVisual** on the prefab root and wire all child references.
5. The **X / Y** fields on PotVisual are populated **per-instance** by hand or by a small spawner — for the simplest case, leave them at default and edit each pot's `X/Y` fields after `KitchenRenderer.Build()` instantiates them. (A future helper can auto-populate from `KitchenLayout.Tiles`.)

## 6. Chef prefab

Build once, used by both online and offline play.

1. Drag a Quaternius `Character_Chef.fbx` into a scene; reset its Transform.
2. Make this the root of a new empty GameObject called `ChefPrefab`. Move the FBX as a child named `Body`.
3. On the root, add components:
   - `NetworkObject` (Netcode)
   - `Grace.Unity.Render.MovementInterpolator` (`tileSize = 1`, `lerpDuration = 0.15`)
   - `Grace.Unity.Render.ChefVisual`
   - `Grace.Unity.Network.NetworkChefAgent`
4. Inside `Body`, add three child empty GameObjects: `HeldOnion`, `HeldDish`, `HeldSoup`. Place the corresponding Food Kit meshes inside, ~at hand-height, **all initially disabled**.
5. (Optional) Add an `Animator` on `Body` with at least a `Walking` bool parameter that drives an Idle/Walk transition.
6. Wire `ChefVisual`:
   - `Interpolator` → root MovementInterpolator
   - `BodyTransform` → child `Body`
   - `HeldOnion / HeldDish / HeldSoup` → corresponding children
   - `BodyAnimator` → optional
   - Leave `NetworkAgent` and `OfflineState` blank — `NetworkChefAgent` lives on the root and `ChefVisual.LateUpdate` finds it via the inspector reference at instance time, or you can drag `NetworkChefAgent` from the same GameObject onto the slot when assembling the prefab.
7. Drag the assembled GameObject into `Assets/Prefabs/ChefPrefab.prefab`.
8. **NetworkManager → Network Prefabs List**: add `ChefPrefab` so it can be spawned over the wire.

## 7. Wire the renderer slots

Open `02_GameRoom.unity`. On the `Kitchen` GameObject (KitchenRenderer):
- Drag each `*Prefab.prefab` into its slot.
- Set `LayoutName = cramped_room`.

On the `PlayerSpawner` GameObject (NetworkPlayerSpawner):
- Drag `ChefPrefab` into `NetworkChefPrefab`.

## 8. Audio import

For each `.wav` / `.ogg` in `Assets/Audio/SFX/`:
- Inspector → **Force To Mono = true**, **Compression = Vorbis**, **Quality = 70%**.

Drop one music loop into `Assets/Audio/BGM/`; mark **Loop**.

Wire AudioMaster (`02_GameRoom`) `Entries` array. One entry per `SfxId` enum value:

| SfxId | Suggested clip(s) |
| --- | --- |
| `Footstep` | 2-3 short footstep variants |
| `Pickup` | a "thunk" / "pop" |
| `Drop` | a softer thud |
| `Interact` | a "click" |
| `Serve` | a "ding" / cash-register-ish chime |
| `RoundStart` | a fanfare |
| `RoundEnd` | a ding-down or crowd cheer |

`Music` slot → an AudioSource child of `AudioMaster` configured to play the BGM clip on awake (loop).

## 9. License attribution (commit later)

Add `unity_env/Assets/Art/CREDITS.md` listing each pack's author + license + URL — required by Kenney/Quaternius CC0 terms (attribution is optional but appreciated; the files themselves are CC0).
