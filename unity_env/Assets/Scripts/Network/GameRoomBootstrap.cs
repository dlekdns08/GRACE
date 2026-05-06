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
            var nm = NetworkManager.Singleton;
            if (nm == null)
            {
                Debug.LogWarning("[GameRoomBootstrap] NetworkManager.Singleton is null; cannot start host.");
                return;
            }
            if (nm.IsListening)
            {
                // Already hosting/joined (came from lobby).
                return;
            }
            if (!nm.StartHost())
            {
                Debug.LogError("[GameRoomBootstrap] StartHost failed.");
            }
        }
    }
}
