// NetworkPlayerSpawner.cs
// Phase G-Network for GRACE.
// See unity_env/GAME_DESIGN.md sections 4 & 5.
//
// Host spawns one NetworkChefAgent per connected player when the game scene
// loads. Each spawn:
//   1) instantiates the NetworkChef prefab and gives ownership to the client,
//   2) assigns the next available 0-based player slot,
//   3) registers (clientId → slot) on NetworkKitchen so SubmitIntentServerRpc
//      can validate sender → slot.
//
// Slots are sticky: once assigned, a client keeps the same slot for the life
// of the kitchen instance, even if other clients disconnect. This avoids
// out-of-bounds writes into NetworkKitchen._intents when NGO clientIds skip.

using Unity.Netcode;
using UnityEngine;

namespace Grace.Unity.Network
{
    /// <summary>
    /// Server-only spawner. Instantiates the network chef prefab once per
    /// connected client, assigns a 0-based player slot, and tells the kitchen
    /// about the (clientId → slot) mapping.
    /// </summary>
    public sealed class NetworkPlayerSpawner : NetworkBehaviour
    {
        public GameObject NetworkChefPrefab;   // assigned via Inspector
        public NetworkKitchen Kitchen;

        /// <summary>Maximum player slots — must match NetworkKitchen.MaxPlayers.</summary>
        public const int MaxSlots = 4;

        // Tracks which slots are in use. Index = slot, value = true iff occupied.
        private readonly bool[] _slotInUse = new bool[MaxSlots];

        public override void OnNetworkSpawn()
        {
            if (!IsServer) return;
            NetworkManager.Singleton.OnClientConnectedCallback += SpawnFor;
            NetworkManager.Singleton.OnClientDisconnectCallback += ReleaseSlot;

            // Host themselves
            SpawnFor(NetworkManager.Singleton.LocalClientId);

            // Already-connected clients (if scene loaded after connection)
            foreach (var clientId in NetworkManager.Singleton.ConnectedClientsIds)
            {
                if (clientId == NetworkManager.Singleton.LocalClientId) continue;
                SpawnFor(clientId);
            }
        }

        private void SpawnFor(ulong clientId)
        {
            int slot = AcquireSlot();
            if (slot < 0)
            {
                Debug.LogWarning($"[NetworkPlayerSpawner] Refusing client {clientId}: all slots full.");
                return;
            }

            var go = Instantiate(NetworkChefPrefab);
            var net = go.GetComponent<NetworkObject>();
            net.SpawnAsPlayerObject(clientId, destroyWithScene: true);

            var chef = go.GetComponent<NetworkChefAgent>();
            if (chef != null)
            {
                chef.Kitchen = Kitchen;
                chef.PlayerIndex.Value = slot;
            }

            if (Kitchen != null) Kitchen.RegisterClientSlot(clientId, slot);
        }

        private int AcquireSlot()
        {
            for (int i = 0; i < _slotInUse.Length; i++)
            {
                if (!_slotInUse[i]) { _slotInUse[i] = true; return i; }
            }
            return -1;
        }

        private void ReleaseSlot(ulong clientId)
        {
            // Best-effort: only release if this client had a registered slot.
            // The kitchen still keeps the entry around (intents from a stale
            // clientId would simply not match any active sender).
            if (Kitchen != null && Kitchen.TryGetClientSlot(clientId, out int slot))
            {
                if (slot >= 0 && slot < _slotInUse.Length) _slotInUse[slot] = false;
            }
        }

        public override void OnNetworkDespawn()
        {
            if (IsServer && NetworkManager.Singleton != null)
            {
                NetworkManager.Singleton.OnClientConnectedCallback -= SpawnFor;
                NetworkManager.Singleton.OnClientDisconnectCallback -= ReleaseSlot;
            }
        }
    }
}
