// LobbyManager.cs
// Phase G-Network for GRACE.
// See unity_env/GAME_DESIGN.md sections 4 & 5.
//
// Title-screen lobby controller: drives RelayBootstrap from UI button events.
// Host creates a Relay allocation and shows the join code; guests enter the
// code and connect. After hosting, the host triggers a network-replicated
// scene load so all clients follow.

using TMPro;
using Unity.Netcode;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace Grace.Unity.Network
{
    /// <summary>
    /// Owns the title-screen interaction with <see cref="RelayBootstrap"/>.
    /// All Inspector references (Relay, UI elements) must be wired in the editor.
    /// </summary>
    public sealed class LobbyManager : MonoBehaviour
    {
        public RelayBootstrap Relay;
        public TMP_InputField JoinCodeInput;
        public TextMeshProUGUI HostJoinCodeDisplay;
        public Button HostButton;
        public Button JoinButton;
        public Button DisconnectButton;
        public string GameSceneName = "02_GameRoom";

        public async void OnHostClicked()
        {
            if (HostButton != null) HostButton.interactable = false;
            string code = await Relay.StartHostWithRelay();
            if (HostJoinCodeDisplay != null) HostJoinCodeDisplay.text = $"Code: {code}";
            // Host loads game scene; clients follow via NetworkSceneManager
            NetworkManager.Singleton.SceneManager.LoadScene(GameSceneName, LoadSceneMode.Single);
        }

        public async void OnJoinClicked()
        {
            if (JoinButton != null) JoinButton.interactable = false;
            string code = JoinCodeInput.text.Trim().ToUpperInvariant();
            await Relay.JoinAsClient(code);
            // Scene load is server-driven once the host issues LoadScene
        }

        public void OnDisconnectClicked()
        {
            Relay.Disconnect();
            if (HostButton != null) HostButton.interactable = true;
            if (JoinButton != null) JoinButton.interactable = true;
            if (HostJoinCodeDisplay != null) HostJoinCodeDisplay.text = "";
        }

        public void OnBackToTitleClicked()
        {
            if (Relay != null) Relay.Disconnect();
            SceneManager.LoadScene("00_Title");
        }
    }
}
