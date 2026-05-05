# 01_Lobby.unity — Manual Build Guide

> Estimated build time: **20 min** (assumes Unity Cloud / Relay is already configured per `unity_env/NETWORK_SETUP.md`).
> Online lobby: host creates a Relay code; guest enters the code to join.

## Prerequisites

- Network setup complete (see `unity_env/NETWORK_SETUP.md` if it exists, or the GAME_DESIGN.md sections 4 & 5).
- Unity Project ID configured in **Edit → Project Settings → Services** (free tier OK).
- Packages installed (already in `Packages/manifest.json`):
  - `com.unity.netcode.gameobjects`
  - `com.unity.services.relay`, `com.unity.services.authentication`, `com.unity.services.core`
  - `com.unity.transport`

## Steps

### 1. Create scene

`[INSPECTOR]` Right-click `Assets/Scenes` → **Create → Scene** → `01_Lobby`. Open it.

### 2. Network manager

`[INSPECTOR]`
1. **GameObject → Create Empty** → name `NetworkManager`.
2. Add components in this order:
   - `NetworkManager` (Netcode for GameObjects)
   - `UnityTransport`
   - `Grace.Unity.Network.RelayBootstrap`
   - `Grace.Unity.Network.NetworkSetup`
3. On `NetworkManager`:
   - Drag the `UnityTransport` component into the **Network Transport** slot.
4. **Mark as DontDestroyOnLoad**: `NetworkSetup` should call `DontDestroyOnLoad(this.gameObject)` in `Awake` — verify in code.

### 3. EventSystem + Canvas

`[INSPECTOR]`
1. **GameObject → UI → Event System**.
2. **GameObject → UI → Canvas** → rename `LobbyCanvas`. Set Canvas Scaler reference resolution to `1920 × 1080`.

### 4. Lobby UI

`[INSPECTOR]` Inside `LobbyCanvas`, build the following:

| GameObject | Type | Purpose |
| --- | --- | --- |
| `TitleText` | TMP Text | "Online Co-op" header |
| `BtnHost` | TMP Button | "Host" |
| `BtnJoin` | TMP Button | "Join" |
| `JoinCodeInput` | TMP Input Field | Where guest types the 6-char code |
| `JoinCodeDisplay` | TMP Text | Where host's code is displayed |
| `StatusText` | TMP Text | Connection status / errors |
| `BtnBack` | TMP Button | "Back to Title" |

Suggested layout: vertical stack centered, fields ~`400 × 60`.

### 5. LobbyManager component

`[INSPECTOR]` Add `Grace.Unity.Network.LobbyManager` to the `NetworkManager` GameObject (or a new `Manager` GameObject — whichever the existing `LobbyManager.cs` expects). Wire its public fields to the corresponding UI elements:
- Host button → `OnHostClicked()`
- Join button → `OnJoinClicked()`
- Code input → `JoinCodeInputField`
- Code display → `JoinCodeDisplayText`
- Status text → `StatusText`

### 6. Camera

`[INSPECTOR]` **GameObject → Camera**. Tag `MainCamera`. Same orthographic UI camera as `00_Title`.

### 7. Save + add to Build Settings

`Ctrl/Cmd-S`. **File → Build Settings → Add Open Scenes**. This scene should be index 1 (after `00_Title`).

## Done when

- [ ] Pressing Host displays a 6-char code in `JoinCodeDisplay` within ~3s.
- [ ] On a second laptop, typing that code in `JoinCodeInput` and pressing Join transitions both clients to `02_GameRoom`.
- [ ] No Console errors related to Relay / Authentication.

## Troubleshooting

- **"You are not signed in"**: `Edit → Project Settings → Services → Sign In` → make sure a Project ID is selected.
- **Relay allocation 401/403**: regenerate API keys via the Unity Cloud dashboard (project must have Relay enabled).
- **Code shows blank**: check `LobbyManager.OnHostClicked` actually awaits the Relay allocation and writes the join code to `JoinCodeDisplayText.text`.
