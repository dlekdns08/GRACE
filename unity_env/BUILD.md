# Build Guide

Per `GAME_DESIGN.md` row 5, GRACE ships for **Mac**, **Windows**, and **WebGL**.
This document covers (a) one-button local builds, and (b) automated CI builds via `.github/workflows/unity-build.yml`.

## Prerequisites

- Unity 2022.3 LTS installed via Unity Hub.
- All four scenes added to **File → Build Settings** in this order:
  1. `Assets/Scenes/00_Title.unity`
  2. `Assets/Scenes/01_Lobby.unity`
  3. `Assets/Scenes/02_GameRoom.unity`
  4. `Assets/Scenes/03_RoundEnd.unity`
- Build target modules added in Unity Hub:
  - **Mac Build Support** (Mono + IL2CPP)
  - **Windows Build Support (IL2CPP)**
  - **WebGL Build Support**

## Local builds (one-shot from the Editor)

### 1. From the Editor menu

`[INSPECTOR]` Use Unity's built-in **File → Build Settings → Build** after switching the active platform from **Switch Platform**. Output goes to wherever you choose.

### 2. From the menu via `BuildScript.cs`

The Editor exposes the same headless entrypoints under **Tools → GRACE Builds** *(future enhancement; for now invoke them from CI or the command line)*.

### 3. Headless from the command line

Each method on `Grace.Unity.EditorTools.BuildScript` writes to a sibling `Builds/` directory inside `unity_env/`.

```bash
# macOS (.app)
/Applications/Unity/Hub/Editor/2022.3.XfX/Unity.app/Contents/MacOS/Unity \
  -batchmode -nographics -quit \
  -projectPath /Users/idaun/PoC/GRACE/unity_env \
  -executeMethod Grace.Unity.EditorTools.BuildScript.BuildMacOS \
  -logFile -

# Windows .exe (must run from a Windows host)
"C:\Program Files\Unity\Hub\Editor\2022.3.XfX\Editor\Unity.exe" ^
  -batchmode -nographics -quit ^
  -projectPath D:\path\to\GRACE\unity_env ^
  -executeMethod Grace.Unity.EditorTools.BuildScript.BuildWindows ^
  -logFile -

# WebGL (works on Mac/Linux/Windows; Builds/webgl/index.html)
/Applications/Unity/Hub/Editor/2022.3.XfX/Unity.app/Contents/MacOS/Unity \
  -batchmode -nographics -quit \
  -projectPath /Users/idaun/PoC/GRACE/unity_env \
  -executeMethod Grace.Unity.EditorTools.BuildScript.BuildWebGL \
  -logFile -
```

The build exits with status `0` on success and `1` on failure (CI fail-fast).

## CI builds

`.github/workflows/unity-build.yml` runs on:
- **Tag pushes** (`v*`) — production releases.
- **Manual workflow dispatch** — for ad-hoc validation.

It uses the [game-ci/unity-builder@v4](https://game.ci/) GitHub Action with three `targetPlatform` matrix entries: `StandaloneOSX`, `StandaloneWindows64`, `WebGL`.

### Required GitHub secrets

| Secret | Where to get it |
| --- | --- |
| `UNITY_LICENSE`  | Free personal license from `unityci/unity-config` workflow, or a Pro `.ulf` |
| `UNITY_EMAIL`    | Unity ID email |
| `UNITY_PASSWORD` | Unity ID password |

See https://game.ci/docs/github/activation for license activation.

### Artifacts

Each platform uploads its build directory as a GitHub Actions artifact named `grace-<targetPlatform>`. Download from the Actions run summary.

## Local cache

The `unity_env/Library/` folder is platform-specific and **must not be committed**. CI restores it from cache keyed on `Assets/**`, `Packages/**`, `ProjectSettings/**` to keep builds fast.

## Build sizes (rough targets)

| Target | Goal | Notes |
| --- | --- | --- |
| macOS  | < 100 MB | IL2CPP, ARM+x64 |
| Windows | < 100 MB | IL2CPP x64 |
| WebGL  | < 50 MB compressed | Brotli on the host; strip ML-Agents path if unused |

## WebGL hosting

For browser-shareable links, copy `unity_env/Builds/webgl/` into `docs/` (root-level, not `unity_env/docs/`) and enable **GitHub Pages → main / docs** in repo settings. The published URL is `https://<user>.github.io/GRACE/`.

## Known gotchas

- **NGO + WebGL**: requires `com.unity.transport >= 2.x` with WebSocket / WebRTC support — already pinned in `Packages/manifest.json`.
- **ML-Agents in WebGL**: not supported. The ML-Agents path is excluded automatically by `Grace.Unity.ML.asmdef`'s define constraints (or it crashes loud at startup; investigate per build).
- **macOS Gatekeeper**: an unsigned `.app` requires `xattr -dr com.apple.quarantine grace.app` before first launch.
