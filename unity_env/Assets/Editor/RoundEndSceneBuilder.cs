// RoundEndSceneBuilder.cs
// Builds Assets/Scenes/03_RoundEnd.unity per 03_RoundEnd.unity.MANUAL.md.
// Run via Tools → GRACE → Build 03_RoundEnd Scene.

using System.IO;
using Grace.Unity.UI;
using TMPro;
using UnityEditor;
using UnityEditor.Events;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Events;

namespace Grace.Unity.EditorTools
{
    public static class RoundEndSceneBuilder
    {
        [MenuItem("Tools/GRACE/Build 03_RoundEnd Scene")]
        public static void Build()
        {
            if (!Directory.Exists(SceneBuildersCommon.ScenesDir))
                Directory.CreateDirectory(SceneBuildersCommon.ScenesDir);

            var scene = SceneBuildersCommon.NewSingleScene("03_RoundEnd");

            SceneBuildersCommon.NewUiCamera();
            SceneBuildersCommon.EnsureEventSystem();

            var canvas = SceneBuildersCommon.NewCanvas("RoundEndCanvas");

            SceneBuildersCommon.NewText(canvas.transform, "TitleText",
                new Vector2(0.5f, 1f), new Vector2(0.5f, 1f),
                new Vector2(0f, -120f), new Vector2(900f, 120f),
                "Round Complete", 80, TextAlignmentOptions.Center);

            var scoreText = SceneBuildersCommon.NewText(canvas.transform, "ScoreText",
                new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f),
                new Vector2(0f, 200f), new Vector2(700f, 100f),
                "Score: 0", 64, TextAlignmentOptions.Center);

            var soupsText = SceneBuildersCommon.NewText(canvas.transform, "SoupsText",
                new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f),
                new Vector2(0f, 100f), new Vector2(700f, 60f),
                "Soups: 0", 40, TextAlignmentOptions.Center);

            var rankText = SceneBuildersCommon.NewText(canvas.transform, "RankText",
                new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f),
                new Vector2(0f, -10f), new Vector2(700f, 100f),
                "Rank: -", 72, TextAlignmentOptions.Center);
            rankText.color = new Color(1f, 0.85f, 0.4f, 1f);

            // RoundEndManager + component
            var managerGO = new GameObject("RoundEndManager");
            var screen = managerGO.AddComponent<RoundEndScreen>();
            screen.ScoreText = scoreText;
            screen.SoupsText = soupsText;
            screen.RankText = rankText;
            screen.TitleScene = "00_Title";
            screen.GameScene = "02_GameRoom";
            screen.RankSScore = 200;
            screen.RankAScore = 120;
            screen.RankBScore = 60;

            var btnPlayAgain = SceneBuildersCommon.NewButton(canvas.transform, "BtnPlayAgain",
                new Vector2(0.5f, 0.5f), new Vector2(0f, -180f), new Vector2(360f, 80f),
                "Play Again");
            UnityEventTools.AddPersistentListener(btnPlayAgain.onClick, new UnityAction(screen.OnPlayAgain));

            var btnTitle = SceneBuildersCommon.NewButton(canvas.transform, "BtnTitle",
                new Vector2(0.5f, 0.5f), new Vector2(0f, -290f), new Vector2(360f, 80f),
                "Back to Title");
            UnityEventTools.AddPersistentListener(btnTitle.onClick, new UnityAction(screen.OnReturnToTitle));

            string scenePath = Path.Combine(SceneBuildersCommon.ScenesDir, "03_RoundEnd.unity");
            SceneBuildersCommon.SaveSceneAndRegister(scene, scenePath);
            Debug.Log($"[GRACE RoundEndSceneBuilder] Built {scenePath}.");
        }
    }
}
