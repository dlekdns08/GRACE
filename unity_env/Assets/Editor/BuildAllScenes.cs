// BuildAllScenes.cs
// One-click full bootstrap: URP pipeline + all four scenes
// (00_Title, 01_Lobby, 02_GameRoom, 03_RoundEnd) + AudioMaster + HUD on
// 02_GameRoom. Run via Tools → GRACE → Build ALL Scenes.

using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Grace.Unity.EditorTools
{
    public static class BuildAllScenes
    {
        [MenuItem("Tools/GRACE/Build ALL Scenes")]
        public static void BuildAll()
        {
            URPSetup.Setup();

            TitleSceneBuilder.Build();
            LobbySceneBuilder.Build();

            // 02_GameRoom: kitchen + HUD + audio in one shot.
            KitchenSceneBuilder.BuildGameRoomScene();
            HUDBuilder.AddHud();
            AudioMasterBuilder.AddAudioMaster();
            EditorSceneManager.SaveOpenScenes();

            RoundEndSceneBuilder.Build();

            // Reorder build settings so indices match the manuals:
            // 00_Title=0, 01_Lobby=1, 02_GameRoom=2, 03_RoundEnd=3.
            var ordered = new System.Collections.Generic.List<EditorBuildSettingsScene>();
            string[] desired =
            {
                "Assets/Scenes/00_Title.unity",
                "Assets/Scenes/01_Lobby.unity",
                "Assets/Scenes/02_GameRoom.unity",
                "Assets/Scenes/03_RoundEnd.unity",
            };
            foreach (var path in desired)
            {
                if (System.IO.File.Exists(path))
                    ordered.Add(new EditorBuildSettingsScene(path, true));
            }
            EditorBuildSettings.scenes = ordered.ToArray();

            Debug.Log("[GRACE BuildAllScenes] Done. Open 00_Title and press Play to walk the full flow.");
        }
    }
}
