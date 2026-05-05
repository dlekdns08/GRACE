// NetworkSetup.cs
// Phase G-Network for GRACE.
// See unity_env/GAME_DESIGN.md sections 4 & 5.
//
// Convenience MonoBehaviour that wires up NetworkManager.Singleton with
// appropriate UnityTransport config. The user attaches this to a
// "NetworkManager" GameObject in the scene; it ensures the GameObject
// survives scene loads via DontDestroyOnLoad.

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
            if (NetworkManager.Singleton == null)
            {
                Debug.LogError("[NetworkSetup] NetworkManager not found. Add the Netcode NetworkManager component to this GameObject.");
                return;
            }
            // Configure UnityTransport to use Relay (set at runtime by RelayBootstrap)
            var transport = NetworkManager.Singleton.GetComponent<UnityTransport>();
            if (transport == null)
            {
                Debug.LogError("[NetworkSetup] UnityTransport component missing on NetworkManager GameObject.");
            }
        }
    }
}
