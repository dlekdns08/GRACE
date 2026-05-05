// RelayBootstrap.cs
// Phase G-Network for GRACE.
// See unity_env/GAME_DESIGN.md sections 4 & 5 (host-authoritative NGO over Unity Relay).
//
// Initializes Unity Services + anonymous Authentication, then either creates
// a Relay allocation (host) or joins one via 6-character join code (guest).

using System.Threading.Tasks;
using Unity.Netcode;
using Unity.Netcode.Transports.UTP;
using Unity.Networking.Transport.Relay;
using Unity.Services.Authentication;
using Unity.Services.Core;
using Unity.Services.Relay;
using Unity.Services.Relay.Models;
using UnityEngine;

namespace Grace.Unity.Network
{
    /// <summary>
    /// Sets up Unity Relay so two players in different networks can connect via a 6-character join code.
    /// Anonymous authentication is used; no Unity account required by players.
    /// </summary>
    public sealed class RelayBootstrap : MonoBehaviour
    {
        public const int MaxConnections = 3;   // host + up to 3 guests = 4 players total
        public string JoinCode { get; private set; }
        public bool IsInitialized { get; private set; }

        public async Task Initialize()
        {
            if (IsInitialized) return;
            await UnityServices.InitializeAsync();
            if (!AuthenticationService.Instance.IsSignedIn)
            {
                await AuthenticationService.Instance.SignInAnonymouslyAsync();
            }
            IsInitialized = true;
        }

        public async Task<string> StartHostWithRelay()
        {
            await Initialize();
            Allocation alloc = await RelayService.Instance.CreateAllocationAsync(MaxConnections);
            JoinCode = await RelayService.Instance.GetJoinCodeAsync(alloc.AllocationId);
            var transport = NetworkManager.Singleton.GetComponent<UnityTransport>();
            transport.SetRelayServerData(new RelayServerData(alloc, "dtls"));
            NetworkManager.Singleton.StartHost();
            return JoinCode;
        }

        public async Task JoinAsClient(string joinCode)
        {
            await Initialize();
            JoinAllocation alloc = await RelayService.Instance.JoinAllocationAsync(joinCode);
            var transport = NetworkManager.Singleton.GetComponent<UnityTransport>();
            transport.SetRelayServerData(new RelayServerData(alloc, "dtls"));
            NetworkManager.Singleton.StartClient();
            JoinCode = joinCode;
        }

        public void Disconnect()
        {
            if (NetworkManager.Singleton == null) return;
            if (NetworkManager.Singleton.IsHost) NetworkManager.Singleton.Shutdown();
            else if (NetworkManager.Singleton.IsClient) NetworkManager.Singleton.Shutdown();
            JoinCode = null;
        }
    }
}
