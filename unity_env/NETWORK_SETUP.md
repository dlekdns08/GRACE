# GRACE — Network Setup Guide

This document covers everything needed to bring up Unity Relay-based 2-player
networking for GRACE. The networking stack is **Netcode for GameObjects (NGO)
1.8** + **Unity Relay** (UGS), host-authoritative simulation, 8 Hz tick rate.

The networking C# is in `Assets/Scripts/Network/`. Most of this guide is
**Inspector + UGS dashboard work** that cannot be expressed in code; every
manual step is tagged `[INSPECTOR]` (Unity Editor) or `[DASHBOARD]` (web UI).

---

## 1. Create / link your Unity Cloud project

Relay is a Unity Gaming Services (UGS) feature, billed per minute of relay
traffic. It has a **generous free tier** that easily covers playtesting.

1. **[DASHBOARD]** Sign in to <https://cloud.unity.com> with your Unity ID
   (free; create one if you don't have one).
2. **[DASHBOARD]** Create a new project (or pick an existing one) at
   <https://cloud.unity.com/home/projects>. Note the **Project ID** —
   you will need it.
3. **[DASHBOARD]** In the project's left sidebar, open
   **Multiplayer → Relay** and click **Enable** (or **Get started**).
4. **[DASHBOARD]** Confirm the project shows Relay as "Active".

---

## 2. Open the Unity project

1. **[INSPECTOR]** Open Unity Hub, click **Add → Add project from disk**, and
   point it at `unity_env/`.
2. **[INSPECTOR]** Open the project with **Unity 2022.3 LTS** (any 2022.3.x
   patch). On first import Unity will resolve the package manifest in
   `Packages/manifest.json`; this fetches:
   - `com.unity.netcode.gameobjects` 1.8.1
   - `com.unity.services.relay` 1.0.5
   - `com.unity.services.authentication` 3.3.3
   - `com.unity.services.core` 1.13.0
   - `com.unity.transport` 2.2.1
   - and the rest of the GRACE deps.

   Resolution may take several minutes the first time.

---

## 3. Link the Editor to your Unity Cloud project

1. **[INSPECTOR]** **Edit → Project Settings → Services**.
2. **[INSPECTOR]** Click **Use an existing Unity project ID** and pick the
   project you created in step 1.2. (This writes
   `ProjectSettings/UnityServicesProjectConfiguration.json` — commit it.)
3. **[INSPECTOR]** In the same panel, scroll to **Relay** and confirm it shows
   as **Enabled** (mirror of the dashboard status).
4. **[INSPECTOR]** Scroll to **Authentication** — anonymous sign-in is enabled
   by default; no action needed.

---

## 4. Build the title scene `00_Title`

> The G2-5 agent owns the master scene MANUAL files. This section documents
> only the **network-related** steps; UI polish is added by G2-5.

### 4.1 Create the NetworkManager GameObject

1. **[INSPECTOR]** Open `Assets/Scenes/00_Title.unity` (create it if missing:
   File → New Scene → Empty, save as `Assets/Scenes/00_Title.unity`).
2. **[INSPECTOR]** Create an empty GameObject named **`NetworkManager`**.
3. **[INSPECTOR]** Add the following components in this order:
   - `NetworkManager` (Netcode for GameObjects)
   - `UnityTransport` (added automatically when NGO asks for a transport — if
     not, **Add Component → Unity Transport**)
   - `RelayBootstrap` (`Grace.Unity.Network.RelayBootstrap`)
   - `NetworkSetup` (`Grace.Unity.Network.NetworkSetup`)
4. **[INSPECTOR]** On `NetworkSetup`, drag the `NetworkManager` GameObject's
   `RelayBootstrap` component into the **Relay** field.
5. **[INSPECTOR]** On `NetworkManager`, leave the **Network Prefabs** list
   empty for now (you'll register the chef prefab in step 5).

### 4.2 Create the Lobby GameObject

1. **[INSPECTOR]** Create an empty GameObject named **`Lobby`**.
2. **[INSPECTOR]** Add component `LobbyManager` (`Grace.Unity.Network.LobbyManager`).
3. **[INSPECTOR]** Drag the `NetworkManager` GameObject into `LobbyManager.Relay`.
4. **[INSPECTOR]** Set `LobbyManager.GameSceneName` to `"02_GameRoom"` (the
   name of the gameplay scene the G2-5 agent will create).

### 4.3 Create the lobby UI

1. **[INSPECTOR]** Create a Canvas: **GameObject → UI → Canvas**.
2. **[INSPECTOR]** Under the canvas, create:
   - A `TMP_InputField` named **`JoinCodeInput`** (placeholder text "Enter
     code"). Mark **Content Type → Standard** and **Character Limit → 6**.
   - A `TextMeshProUGUI` named **`HostCodeDisplay`** (initially blank text).
   - A `Button` named **`HostButton`** with label "Host".
   - A `Button` named **`JoinButton`** with label "Join".
   - A `Button` named **`DisconnectButton`** with label "Disconnect".
3. **[INSPECTOR]** Wire `LobbyManager` Inspector fields:
   - `JoinCodeInput` → drag the input field
   - `HostJoinCodeDisplay` → drag the host code text
   - `HostButton` / `JoinButton` / `DisconnectButton` → drag the buttons
4. **[INSPECTOR]** On each button's **OnClick()** event, add the corresponding
   `LobbyManager` callback:
   - `HostButton.OnClick` → `LobbyManager.OnHostClicked`
   - `JoinButton.OnClick` → `LobbyManager.OnJoinClicked`
   - `DisconnectButton.OnClick` → `LobbyManager.OnDisconnectClicked`
5. **[INSPECTOR]** Save the scene.

---

## 5. Create the NetworkChef prefab

The host spawns one of these per connected player; each is owned by its
client.

1. **[INSPECTOR]** In the Project window, create
   `Assets/Prefabs/NetworkChef.prefab` (right-click → Create → Prefab).
2. **[INSPECTOR]** Open the prefab, add components:
   - `NetworkObject` (Netcode) — leave default settings
   - `NetworkChefAgent` (`Grace.Unity.Network.NetworkChefAgent`)
   - The **ChefVisual** components from the G2-5 agent's render layer
     (mesh / animator / interpolator) — added when G2-5 lands.
3. **[INSPECTOR]** Save the prefab.
4. **[INSPECTOR]** Back in the title scene, on the `NetworkManager`
   GameObject's **NetworkManager.NetworkConfig.NetworkPrefabs** list:
   - Click **+** and drop `NetworkChef.prefab` in.
   - Mark **Override = None** (default), **Player Prefab** = `NetworkChef.prefab`
     (sets it as the auto-spawn player object).

> **Why a Player Prefab _and_ a NetworkPlayerSpawner?**
> NGO will auto-spawn a player object when a client connects, **but only if
> the gameplay scene is loaded for that client**. Because GRACE uses a Lobby
> → Game scene transition driven by `NetworkManager.SceneManager.LoadScene`,
> we add a `NetworkPlayerSpawner` in the gameplay scene to spawn chefs
> deterministically once everyone has the scene. You can disable the auto
> Player Prefab by clearing it on `NetworkManager.NetworkConfig`; either
> approach works as long as exactly one chef is spawned per client.

---

## 6. Build the gameplay scene `02_GameRoom`

> Most of this scene's contents are owned by G2-5 (rendering, audio, HUD).
> Network-relevant steps only:

1. **[INSPECTOR]** Create `Assets/Scenes/02_GameRoom.unity`.
2. **[INSPECTOR]** **Build Settings → Add Open Scenes** to register both
   `00_Title` (index 0) and `02_GameRoom` (index 1).
3. **[INSPECTOR]** In `02_GameRoom`, create a GameObject **`Kitchen`** with
   the `NetworkKitchen` component (`Grace.Unity.Network.NetworkKitchen`).
   - On the GameObject, also add `NetworkObject`. Mark it **scene-placed**
     (do not save in any prefab the title scene loads).
   - Set `NetworkKitchen.LayoutName` to `"cramped_room"` (or another value
     from `Assets/Resources/Layouts/`).
4. **[INSPECTOR]** Create a GameObject **`PlayerSpawner`** with
   `NetworkPlayerSpawner`.
   - Drop the `NetworkChef.prefab` into the `NetworkChefPrefab` field.
   - Drop the `Kitchen` GameObject into the `Kitchen` field.
5. **[INSPECTOR]** Save the scene.

---

## 7. Smoke test — single machine, two editor instances

Easiest way to verify Relay end-to-end without a build:

1. **[INSPECTOR]** **File → Open Scene** → `00_Title.unity`.
2. **[INSPECTOR]** Press **Play**. Click **Host**. The `HostCodeDisplay` will
   show `Code: ABC123`. Copy that string.
3. Open a second copy of the project (Unity Hub supports cloning the project
   directory; or use the **ParrelSync** package). In the second editor,
   open `00_Title`, press Play.
4. Paste the code into the join field, click **Join**.
5. The host's `LobbyManager.OnHostClicked` triggers
   `NetworkManager.SceneManager.LoadScene("02_GameRoom")`; both editors
   should switch to the gameplay scene.
6. Confirm in the host's Console: `NetworkObject … is now spawned` for each
   chef. Move with WASD/arrows on each client.

---

## 8. Smoke test — across the internet

1. **[INSPECTOR]** **File → Build Settings → Build** (Mac/Win/Linux). Run the
   build on a second machine.
2. Have one machine click **Host**, share the 6-character code over chat.
3. The other machine pastes the code, clicks **Join**.
4. Check `Stats Monitor` (Window → Analysis → Profiler) for RTT and
   bandwidth — expected RTT 60-150 ms, bandwidth < 5 KB/s/player at 8 Hz.

---

## 9. Reconnection caveat (v1)

Reconnection is **not implemented** in v1. If a guest disconnects:

- The host's `NetworkKitchen.IsRunning.Value` keeps the simulation paused
  only if you wire it to the `NetworkManager.OnClientDisconnectCallback`.
  By default, the simulation continues with the disconnecting player's
  intents stuck at `0 = STAY`.
- Recommended UX: in `LobbyManager` (or a future `MatchManager`), subscribe
  to `NetworkManager.Singleton.OnClientDisconnectCallback` on the host and
  set `kitchen.IsRunning.Value = false` until the guest rejoins or the host
  clicks Disconnect.

---

## 10. Files reference

- `Assets/Scripts/Network/RelayBootstrap.cs` — UGS init + Relay alloc/join
- `Assets/Scripts/Network/NetworkSetup.cs` — DontDestroyOnLoad for the
  `NetworkManager` GameObject; sanity checks
- `Assets/Scripts/Network/NetworkKitchen.cs` — host-authoritative tick loop +
  replicated state (chefs, pots, score, step)
- `Assets/Scripts/Network/NetworkChefAgent.cs` — per-player network proxy
  (intent submission + replicated state read)
- `Assets/Scripts/Network/NetworkPlayerSpawner.cs` — host-only chef spawner
- `Assets/Scripts/Network/LobbyManager.cs` — title-screen UI controller
- `Assets/Scripts/Network/Grace.Unity.Network.asmdef` — assembly definition
- `Tests/EditMode/Network/NetworkSerializationTests.cs` — EditMode tests for
  `ChefStateNet` / `PotStateNet` round-trip and equality

---

## 11. Troubleshooting

- **"Relay request failed: 401 Unauthorized"** → Authentication did not sign
  in. Confirm step 3.4. Try clicking **Edit → Clear Project Cache** in the
  Services panel and Play again.
- **"Relay allocation succeeded but client cannot connect"** → DTLS handshake
  failed. Check that both clients use the same Unity project ID; Relay
  allocations are scoped to a single project.
- **Player object spawns twice** → You enabled **Player Prefab** on
  `NetworkManager.NetworkConfig` *and* `NetworkPlayerSpawner` is also
  spawning. Clear the Player Prefab field, or remove `NetworkPlayerSpawner`.
- **`NetworkList<ChefStateNet>` constructor error** → NGO 1.8 requires
  `NetworkList` instances to be constructed in `Awake()` (or inline as a
  field initializer), **not** in `OnNetworkSpawn()`. `NetworkKitchen.cs`
  does this in `Awake()`.

---

## 12. NGO 1.8 API caveats

A few things worth knowing if you extend the network code:

- `NetworkList<T>` requires `T : INetworkSerializable, IEquatable<T>` and a
  parameterless constructor. The `Equals` override is **mandatory**;
  without it, dirty-checking falls back to `Object.Equals` and burns CPU.
- `NetworkVariable<T>` parameterless `new()` constructor (used in
  `NetworkKitchen`) is allowed in NGO 1.8 because of C# 9 record-style
  defaults; older snippets used `new NetworkVariable<int>(0, …)`.
- `RelayServerData(alloc, "dtls")` overload requires
  `Unity.Networking.Transport` 2.x. If your manifest pins 1.x, use
  `alloc.ToRelayServerData("dtls")` (extension method) instead.
- `NetworkManager.SceneManager.LoadScene` only works after `StartHost()` /
  `StartServer()` has succeeded; calling it from the lobby before relaying
  is up will throw a NullReferenceException.
