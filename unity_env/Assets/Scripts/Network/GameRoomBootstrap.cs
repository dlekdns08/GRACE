// GameRoomBootstrap.cs
// Ensures the game scene has a running NetworkManager session.
//
// If the scene is entered from the title via Local Co-op / Solo vs AI (offline)
// or directly via Play in the editor (no prior scene), this auto-calls
// StartHost so NetworkKitchen's server-only simulation actually ticks.
// If the user came in from 01_Lobby (online), NetworkManager.IsListening is
// already true and we leave it alone.

using Unity.Netcode;
using UnityEngine;

namespace Grace.Unity.Network
{
    /// <summary>Bootstraps a host session in the game scene when none is active.</summary>
    public sealed class GameRoomBootstrap : MonoBehaviour
    {
        private void Start()
        {
            Debug.Log("[GameRoomBootstrap] Start() running.");
            var nm = NetworkManager.Singleton;
            if (nm == null)
            {
                Debug.LogError("[GameRoomBootstrap] NetworkManager.Singleton is null; cannot start host.");
                return;
            }
            if (nm.IsListening)
            {
                Debug.Log("[GameRoomBootstrap] NetworkManager already listening; not starting a new host.");
                return;
            }
            Debug.Log("[GameRoomBootstrap] Calling StartHost()…");
            bool ok = nm.StartHost();
            Debug.Log($"[GameRoomBootstrap] StartHost returned {ok}. IsHost={nm.IsHost} IsServer={nm.IsServer} IsListening={nm.IsListening}");
            if (!ok)
            {
                Debug.LogError("[GameRoomBootstrap] StartHost failed. Check transport / port / network prefab list.");
            }
        }
    }
}
