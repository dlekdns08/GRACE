# 00_Title.unity — Manual Build Guide

> Estimated build time: **15 min**.
> A `.unity` scene cannot be authored as plain text, so this document walks through the Editor steps to build the title screen scene from scratch.

## Prerequisites

- Unity 2022.3 LTS open on `unity_env/`.
- All scripts compiled (no red errors in Console). The first compile after pulling will take ~30s.
- TextMeshPro Essentials imported (`Window → TextMeshPro → Import TMP Essential Resources`) the first time you open the project.

## Steps

### 1. Create the scene

`[INSPECTOR]` In the Project window:
1. Right-click `Assets/Scenes` → **Create → Scene** → name it `00_Title`.
2. Double-click `00_Title` to open it.
3. Delete the default `Main Camera` and `Directional Light` if present — we'll recreate URP-friendly versions.

### 2. Camera

`[INSPECTOR]`
1. **GameObject → Camera** → rename to `MainCamera`.
2. Tag it `MainCamera`.
3. In the Inspector, set:
   - **Clear Flags**: `Solid Color`
   - **Background**: any dark color (e.g. `#1B1F2A`)
   - **Projection**: `Orthographic`, **Size**: `5`
   - **Position**: `(0, 1, -10)`
4. Add component **Universal Additional Camera Data** (URP auto-adds it on first render; no action needed if URP is the active pipeline).

### 3. EventSystem

`[INSPECTOR]` **GameObject → UI → Event System** (creates an `EventSystem` GameObject; required for UI button clicks).

### 4. Canvas

`[INSPECTOR]`
1. **GameObject → UI → Canvas**. Rename to `TitleCanvas`.
2. On the `Canvas` component:
   - **Render Mode**: `Screen Space - Overlay`
3. On the `Canvas Scaler`:
   - **UI Scale Mode**: `Scale With Screen Size`
   - **Reference Resolution**: `1920 × 1080`
   - **Match**: `0.5`

### 5. Title text

`[INSPECTOR]` Right-click `TitleCanvas` → **UI → Text - TextMeshPro** → name it `TitleText`.
- **Text**: `GRACE`
- **Font Size**: `200`
- **Alignment**: `Center / Middle`
- **Color**: white
- **Rect Transform**: anchor presets → top-center; `Pos Y = -250`; `Width = 800; Height = 250`

### 6. Subtitle (optional)

`[INSPECTOR]` Add a second TMP text under `TitleCanvas` named `Subtitle`:
- Text: `Cooperative cooking, Carroll-faithful.`
- Font Size: `36`
- Anchor below `TitleText`

### 7. Three buttons

`[INSPECTOR]` For each of `BtnLocalCoop`, `BtnOnlineCoop`, `BtnSoloAI`:
1. Right-click `TitleCanvas` → **UI → Button - TextMeshPro**.
2. Rename and set the child `Text (TMP)` text accordingly:
   - `BtnLocalCoop`  → "Local Co-op"
   - `BtnOnlineCoop` → "Online Co-op"
   - `BtnSoloAI`     → "Solo vs AI"
3. Stack them vertically, centered. Suggested layout:
   - `BtnLocalCoop`:  `Pos Y = 50`
   - `BtnOnlineCoop`: `Pos Y = -50`
   - `BtnSoloAI`:     `Pos Y = -150`
   - All `Width = 360; Height = 80`.

(Optional) Add `BtnQuit` at the bottom for desktop builds.

### 8. Manager GameObject + TitleMenu component

`[INSPECTOR]`
1. **GameObject → Create Empty** → name `Manager`.
2. **Add Component → TitleMenu** (search by name).
3. The TitleMenu fields default to `00_Title`/`01_Lobby`/`02_GameRoom`. Override only if you renamed scenes.

### 9. Wire button OnClick events

`[INSPECTOR]` For each button, in its `Button (Script)` component:
1. Press `+` under **OnClick ()**.
2. Drag `Manager` into the object slot.
3. From the function dropdown choose `TitleMenu → OnLocalCoop()` (etc., per button).

| Button | Function |
| --- | --- |
| `BtnLocalCoop`  | `TitleMenu.OnLocalCoop()` |
| `BtnOnlineCoop` | `TitleMenu.OnOnlineCoop()` |
| `BtnSoloAI`     | `TitleMenu.OnSoloAI()` |
| `BtnQuit`       | `TitleMenu.OnQuit()` |

### 10. Save

`Ctrl/Cmd-S`. Then **File → Build Settings → Add Open Scenes** so this scene becomes index 0.

## Done when

- [ ] Pressing **Play** shows "GRACE" + 3 (or 4) buttons.
- [ ] Clicking `Local Co-op` loads `02_GameRoom`.
- [ ] Clicking `Online Co-op` loads `01_Lobby`.
- [ ] Clicking `Solo vs AI` loads `02_GameRoom`.
- [ ] No Console errors.
