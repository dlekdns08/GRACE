// NetworkChefAgent.cs
// Phase G-Network for GRACE.
// See unity_env/GAME_DESIGN.md sections 4 & 5.
//
// Per-player network proxy. The owning client submits action intents to the
// host's NetworkKitchen via ServerRpc (which derives the player slot from the
// verified sender clientId). All clients read the replicated state from
// NetworkKitchen.Chefs.

using Unity.Netcode;
using UnityEngine;

namespace Grace.Unity.Network
{
    /// <summary>
    /// Per-player network proxy. Owner submits action intents to the host's
    /// NetworkKitchen. The kitchen maps the sender clientId to a player slot
    /// (assigned at spawn time by NetworkPlayerSpawner); the slot is also
    /// replicated here for read-only consumers (HUD, ChefVisual).
    /// </summary>
    public sealed class NetworkChefAgent : NetworkBehaviour
    {
        /// <summary>Server-assigned player slot (0-based). Replicated to all clients.</summary>
        public NetworkVariable<int> PlayerIndex = new(
            -1,
            readPerm: NetworkVariableReadPermission.Everyone,
            writePerm: NetworkVariableWritePermission.Server);

        public NetworkKitchen Kitchen;

        public override void OnNetworkSpawn()
        {
            // Resolve a Kitchen reference if not pre-assigned by the spawner.
            if (Kitchen == null) Kitchen = FindAnyObjectByType<NetworkKitchen>();
        }

        /// <summary>
        /// Called by the owning client each tick (8 Hz). The kitchen ignores the
        /// RPC if the sender has no registered slot.
        /// </summary>
        public void SubmitAction(int action)
        {
            if (!IsOwner) return;
            if (Kitchen == null) Kitchen = FindAnyObjectByType<NetworkKitchen>();
            if (Kitchen == null) return;
            Kitchen.SubmitIntentServerRpc(action);
        }

        /// <summary>For renderers/HUD — gets the most recent replicated state for this chef.</summary>
        public ChefStateNet? CurrentState
        {
            get
            {
                if (Kitchen == null) return null;
                int idx = PlayerIndex.Value;
                if (idx < 0 || idx >= Kitchen.Chefs.Count) return null;
                return Kitchen.Chefs[idx];
            }
        }
    }
}
