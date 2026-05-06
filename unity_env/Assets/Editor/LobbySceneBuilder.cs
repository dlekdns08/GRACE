// LobbySceneBuilder.cs
// Builds Assets/Scenes/01_Lobby.unity per 01_Lobby.unity.MANUAL.md.
// Run via Tools → GRACE → Build 01_Lobby Scene.

using System.IO;
using Grace.Unity.Network;
using TMPro;
using Unity.Netcode;
using Unity.Netcode.Transports.UTP;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Events;

namespace Grace.Unity.EditorTools
{
    public static class LobbySceneBuilder
    {
        [MenuItem("Tools/GRACE/Build 01_Lobby Scene")]
        public static void Build()
        {
            if (!Directory.Exists(SceneBuildersCommon.ScenesDir))
                Directory.CreateDirectory(SceneBuildersCommon.ScenesDir);

            var scene = SceneBuildersCommon.NewSingleScene("01_Lobby");

            SceneBuildersCommon.NewUiCamera();
            SceneBuildersCommon.EnsureEventSystem();

            // NetworkManager + Transport + Relay + NetworkSetup + LobbyManager
            var nmGO = new GameObject("NetworkManager");
            var nm = nmGO.AddComponent<NetworkManager>();
            var transport = nmGO.AddComponent<UnityTransport>();
            nm.NetworkConfig = new NetworkConfig
            {
                NetworkTransport = transport,
                ConnectionApproval = false,
            };
            var relay = nmGO.AddComponent<RelayBootstrap>();
            var netSetup = nmGO.AddComponent<NetworkSetup>();
            netSetup.Relay = relay;
            var lobby = nmGO.AddComponent<LobbyManager>();
            lobby.Relay = relay;
            lobby.GameSceneName = "02_GameRoom";

            // Canvas
            var canvas = SceneBuildersCommon.NewCanvas("LobbyCanvas");

            SceneBuildersCommon.NewText(canvas.transform, "TitleText",
                new Vector2(0.5f, 1f), new Vector2(0.5f, 1f),
                new Vector2(0f, -120f), new Vector2(900f, 120f),
                "Online Co-op", 96, TextAlignmentOptions.Center);

            var btnHost = SceneBuildersCommon.NewButton(canvas.transform, "BtnHost",
                new Vector2(0.5f, 0.5f), new Vector2(0f, 200f), new Vector2(400f, 80f),
                "Host");
            lobby.HostButton = btnHost;
            UnityEventTools.AddPersistentListener(btnHost.onClick, new UnityAction(lobby.OnHostClicked));

            var hostCode = SceneBuildersCommon.NewText(canvas.transform, "JoinCodeDisplay",
                new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f),
                new Vector2(0f, 110f), new Vector2(700f, 60f),
                "", 40, TextAlignmentOptions.Center);
            lobby.HostJoinCodeDisplay = hostCode as TextMeshProUGUI;

            var input = SceneBuildersCommon.NewInputField(canvas.transform, "JoinCodeInput",
                new Vector2(0.5f, 0.5f), new Vector2(0f, 0f), new Vector2(400f, 60f),
                "Enter code");
            lobby.JoinCodeInput = input;

            var btnJoin = SceneBuildersCommon.NewButton(canvas.transform, "BtnJoin",
                new Vector2(0.5f, 0.5f), new Vector2(0f, -90f), new Vector2(400f, 80f),
                "Join");
            lobby.JoinButton = btnJoin;
            UnityEventTools.AddPersistentListener(btnJoin.onClick, new UnityAction(lobby.OnJoinClicked));

            SceneBuildersCommon.NewText(canvas.transform, "StatusText",
                new Vector2(0.5f, 0f), new Vector2(0.5f, 0f),
                new Vector2(0f, 200f), new Vector2(900f, 60f),
                "", 28, TextAlignmentOptions.Center);

            var btnBack = SceneBuildersCommon.NewButton(canvas.transform, "BtnBack",
                new Vector2(0.5f, 0f), new Vector2(0f, 80f), new Vector2(300f, 60f),
                "Back to Title", 24f);
            UnityEventTools.AddPersistentListener(
                btnBack.onClick, new UnityAction(lobby.OnBackToTitleClicked));

            string scenePath = Path.Combine(SceneBuildersCommon.ScenesDir, "01_Lobby.unity");
            SceneBuildersCommon.SaveSceneAndRegister(scene, scenePath);
            Debug.Log($"[GRACE LobbySceneBuilder] Built {scenePath}.");
        }
    }
}
