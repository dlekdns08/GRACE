// TitleMenu.cs
// Phase G3 (UI layer) for GRACE.
//
// Three-button title screen: Local Co-op, Online Co-op, Solo vs AI.
// Wire each button's OnClick to the matching public method in the Inspector.

using UnityEngine;
using UnityEngine.SceneManagement;

namespace Grace.Unity.UI
{
    /// <summary>Title-screen mode selector; loads the appropriate scene per mode.</summary>
    public sealed class TitleMenu : MonoBehaviour
    {
        [Header("Scene names (must match Build Settings entries)")]
        public string LocalScene = "02_GameRoom";
        public string LobbyScene = "01_Lobby";
        public string SoloScene = "02_GameRoom";

        public void OnLocalCoop()
        {
            GameModeFlags.IsOnline = false;
            GameModeFlags.IsSoloVsAI = false;
            SceneManager.LoadScene(LocalScene);
        }

        public void OnOnlineCoop()
        {
            GameModeFlags.IsOnline = true;
            GameModeFlags.IsSoloVsAI = false;
            SceneManager.LoadScene(LobbyScene);
        }

        public void OnSoloAI()
        {
            GameModeFlags.IsOnline = false;
            GameModeFlags.IsSoloVsAI = true;
            SceneManager.LoadScene(SoloScene);
        }

        public void OnQuit()
        {
#if UNITY_EDITOR
            UnityEditor.EditorApplication.isPlaying = false;
#else
            Application.Quit();
#endif
        }
    }

    /// <summary>Cross-scene flags for the chosen game mode and selected layout.</summary>
    public static class GameModeFlags
    {
        public static bool IsOnline;
        public static bool IsSoloVsAI;
        public static string SelectedLayout = "cramped_room";
    }
}
