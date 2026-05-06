// NetworkSetup.cs
// Phase G-Network for GRACE.
// See unity_env/GAME_DESIGN.md sections 4 & 5.
//
// Convenience MonoBehaviour that wires up NetworkManager.Singleton with
// appropriate UnityTransport config. The user attaches this to a
// "NetworkManager" GameObject in the scene; it ensures the GameObject
// survives scene loads via DontDestroyOnLoad.

using System.Reflection;
using Unity.Netcode;
using Unity.Netcode.Transports.UTP;
using UnityEngine;

namespace Grace.Unity.Network
{
    /// <summary>
    /// Marks the GameObject hosting <see cref="NetworkManager"/> + <see cref="UnityTransport"/>
    /// as <c>DontDestroyOnLoad</c> and validates that required components are present.
    /// </summary>
    public sealed class NetworkSetup : MonoBehaviour
    {
        public RelayBootstrap Relay;

        private void Awake()
        {
            DontDestroyOnLoad(gameObject);
        }

        private void Start()
        {
            var nm = NetworkManager.Singleton ?? GetComponent<NetworkManager>();
            if (nm == null)
            {
                Debug.LogError("[NetworkSetup] NetworkManager not found. Add the Netcode NetworkManager component to this GameObject.");
                return;
            }
            if (nm.GetComponent<UnityTransport>() == null)
            {
                Debug.LogError("[NetworkSetup] UnityTransport component missing on NetworkManager GameObject.");
                return;
            }

            // If we entered the game scene directly (e.g. pressed Play in
            // 02_GameRoom while developing) and no host was started by an
            // earlier scene like 01_Lobby, start one now so NetworkKitchen's
            // server-only simulation actually ticks. Skipped when we're
            // already hosting/joined.
            string activeScene = UnityEngine.SceneManagement.SceneManager.GetActiveScene().name;
            if (!nm.IsListening && activeScene == "02_GameRoom")
            {
                // Register PlayerPrefab in the prefab table before StartHost so
                // NetworkPlayerSpawner.SpawnAsPlayerObject (and NGO's auto-
                // player-spawn) succeed without "Prefab not found" errors when
                // ForceSamePrefabs is enabled.
                if (nm.NetworkConfig.PlayerPrefab != null
                    && nm.NetworkConfig.Prefabs != null
                    && !nm.NetworkConfig.Prefabs.Contains(nm.NetworkConfig.PlayerPrefab))
                {
                    nm.AddNetworkPrefab(nm.NetworkConfig.PlayerPrefab);
                    Debug.Log("[NetworkSetup] Registered PlayerPrefab with NGO prefab table.");
                }

                // Last-line-of-defense: if any scene-placed NetworkObject still
                // has GlobalObjectIdHash == 0 (e.g. scaffold added it
                // programmatically and OnValidate never ran), fix it before
                // StartHost — otherwise NGO throws "ScenePlacedObjects already
                // contains hash 0" and the host never starts.
                FixZeroNetworkObjectHashes();

                Debug.Log("[NetworkSetup] No active host detected in 02_GameRoom; calling StartHost().");
                bool ok = nm.StartHost();
                Debug.Log($"[NetworkSetup] StartHost returned {ok}. IsHost={nm.IsHost} IsServer={nm.IsServer} IsListening={nm.IsListening}");
                if (!ok)
                {
                    Debug.LogError("[NetworkSetup] StartHost failed. Inspect transport / prefab list.");
                }
            }
        }

        private static void FixZeroNetworkObjectHashes()
        {
            var hashField = typeof(NetworkObject).GetField(
                "GlobalObjectIdHash",
                BindingFlags.Instance | BindingFlags.NonPublic);
            if (hashField == null) return;

            var seen = new System.Collections.Generic.HashSet<uint>();
            foreach (var no in Object.FindObjectsByType<NetworkObject>(FindObjectsSortMode.None))
            {
                uint h = (uint)hashField.GetValue(no);
                if (h == 0u || !seen.Add(h))
                {
                    string path = no.gameObject.scene.name + "/" + no.gameObject.name;
                    uint candidate = unchecked((uint)path.GetHashCode());
                    if (candidate == 0u) candidate = 1u;
                    while (seen.Contains(candidate)) candidate++;
                    hashField.SetValue(no, candidate);
                    seen.Add(candidate);
                    Debug.Log($"[NetworkSetup] Patched GlobalObjectIdHash for '{no.gameObject.name}' → {candidate} (was {h}).");
                }
            }
        }
    }
}
