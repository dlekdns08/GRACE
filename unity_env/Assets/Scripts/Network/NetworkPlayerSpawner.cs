// NetworkPlayerSpawner.cs
// Phase G-Network for GRACE.
// See unity_env/GAME_DESIGN.md sections 4 & 5.
//
// Host spawns one NetworkChefAgent per connected player when the game scene
// loads. Each spawned NetworkObject is owned by its corresponding client.

using Unity.Netcode;
using UnityEngine;

namespace Grace.Unity.Network
{
    /// <summary>
    /// Server-only spawner. Instantiates the network chef prefab once per
    /// connected client and assigns ownership.
    /// </summary>
    public sealed class NetworkPlayerSpawner : NetworkBehaviour
    {
        public GameObject NetworkChefPrefab;   // assigned via Inspector
        public NetworkKitchen Kitchen;

        public override void OnNetworkSpawn()
        {
            if (!IsServer) return;
            NetworkManager.Singleton.OnClientConnectedCallback += SpawnFor;

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
            var go = Instantiate(NetworkChefPrefab);
            var net = go.GetComponent<NetworkObject>();
            net.SpawnAsPlayerObject(clientId, destroyWithScene: true);
            var chef = go.GetComponent<NetworkChefAgent>();
            if (chef != null) chef.Kitchen = Kitchen;
        }

        public override void OnNetworkDespawn()
        {
            if (IsServer && NetworkManager.Singleton != null)
            {
                NetworkManager.Singleton.OnClientConnectedCallback -= SpawnFor;
            }
        }
    }
}
