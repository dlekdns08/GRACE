// NetworkChefAgent.cs
// Phase G-Network for GRACE.
// See unity_env/GAME_DESIGN.md sections 4 & 5.
//
// Per-player network proxy. The owning client submits action intents to the
// host's NetworkKitchen via ServerRpc. All clients read the replicated state
// from NetworkKitchen.Chefs.

using Unity.Netcode;
using UnityEngine;

namespace Grace.Unity.Network
{
    /// <summary>
    /// Per-player network proxy. Owner submits action intents to the host's NetworkKitchen.
    /// All clients read replicated state (position/facing/held) from NetworkKitchen.Chefs.
    /// </summary>
    public sealed class NetworkChefAgent : NetworkBehaviour
    {
        public int PlayerIndex { get; private set; }
        public NetworkKitchen Kitchen;

        public override void OnNetworkSpawn()
        {
            // Owner client-id → playerIndex mapping (host = 0, first client = 1, etc.)
            PlayerIndex = (int)OwnerClientId;
        }

        /// <summary>
        /// Called by PlayerInputController each tick on the owning client.
        /// </summary>
        public void SubmitAction(int action)
        {
            if (!IsOwner) return;
            if (Kitchen == null) Kitchen = FindFirstObjectByType<NetworkKitchen>();
            if (Kitchen == null) return;
            Kitchen.SubmitIntentServerRpc(PlayerIndex, action);
        }

        /// <summary>For renderers/HUD — gets the most recent replicated state for this chef.</summary>
        public ChefStateNet? CurrentState
        {
            get
            {
                if (Kitchen == null) return null;
                if (PlayerIndex < 0 || PlayerIndex >= Kitchen.Chefs.Count) return null;
                return Kitchen.Chefs[PlayerIndex];
            }
        }
    }
}
