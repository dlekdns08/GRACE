// RoundEndCoordinator.cs
// Phase G-Network for GRACE.
//
// Watches NetworkKitchen.IsRunning. When it flips false (max-step reached or
// host-stopped), the host snapshots the final score / soups into a
// DontDestroyOnLoad payload and triggers a network-replicated scene load to
// the round-end screen.

using Grace.Unity.Core;
using Unity.Netcode;
using UnityEngine;

namespace Grace.Unity.Network
{
    /// <summary>
    /// Server-driven trigger that ends the round when the kitchen stops running.
    /// Drop one of these into the gameplay scene next to NetworkKitchen.
    /// </summary>
    [RequireComponent(typeof(NetworkObject))]
    public sealed class RoundEndCoordinator : NetworkBehaviour
    {
        [Tooltip("Kitchen to observe. Auto-resolved if left empty.")]
        public NetworkKitchen Kitchen;

        [Tooltip("Scene to load when the round ends.")]
        public string RoundEndScene = "03_RoundEnd";

        private bool _ended;

        public override void OnNetworkSpawn()
        {
            if (!IsServer) return;
            if (Kitchen == null) Kitchen = FindFirstObjectByType<NetworkKitchen>();
            if (Kitchen != null)
                Kitchen.IsRunning.OnValueChanged += OnRunningChanged;
        }

        public override void OnNetworkDespawn()
        {
            if (Kitchen != null)
                Kitchen.IsRunning.OnValueChanged -= OnRunningChanged;
        }

        private void OnRunningChanged(bool prev, bool next)
        {
            if (_ended || next || !IsServer) return;
            _ended = true;

            RoundResults.Last = new RoundResults.Snapshot
            {
                Score = Kitchen.Score.Value,
                Soups = Kitchen.SoupsServed.Value,
                Steps = Kitchen.Step.Value,
            };
            // NetworkSceneManager replicates the load to all connected clients.
            NetworkManager.Singleton.SceneManager.LoadScene(
                RoundEndScene, UnityEngine.SceneManagement.LoadSceneMode.Single);
        }
    }

    /// <summary>
    /// Static carrier for cross-scene round results. Lives in process memory;
    /// each client reads its own copy from <see cref="Last"/> on the round-end
    /// scene. The host's network-replicated scene load happens before clients
    /// read this, but the values are independently re-derivable from the last
    /// observed NetworkKitchen state if needed.
    /// </summary>
    public static class RoundResults
    {
        public struct Snapshot
        {
            public int Score;
            public int Soups;
            public int Steps;
        }

        public static Snapshot Last;
    }
}
