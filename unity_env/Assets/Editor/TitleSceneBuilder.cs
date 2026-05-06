// TitleSceneBuilder.cs
// Builds Assets/Scenes/00_Title.unity per 00_Title.unity.MANUAL.md.
// Run via Tools → GRACE → Build 00_Title Scene.

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
    public static class TitleSceneBuilder
    {
        [MenuItem("Tools/GRACE/Build 00_Title Scene")]
        public static void Build()
        {
            if (!Directory.Exists(SceneBuildersCommon.ScenesDir))
                Directory.CreateDirectory(SceneBuildersCommon.ScenesDir);

            var scene = SceneBuildersCommon.NewSingleScene("00_Title");

            SceneBuildersCommon.NewUiCamera();
            SceneBuildersCommon.EnsureEventSystem();

            var canvas = SceneBuildersCommon.NewCanvas("TitleCanvas");

            SceneBuildersCommon.NewText(canvas.transform, "TitleText",
                new Vector2(0.5f, 1f), new Vector2(0.5f, 1f),
                new Vector2(0f, -250f), new Vector2(800f, 250f),
                "GRACE", 200, TextAlignmentOptions.Center);

            SceneBuildersCommon.NewText(canvas.transform, "Subtitle",
                new Vector2(0.5f, 1f), new Vector2(0.5f, 1f),
                new Vector2(0f, -440f), new Vector2(900f, 60f),
                "Cooperative cooking, Carroll-faithful.", 36, TextAlignmentOptions.Center);

            // Manager + TitleMenu component (must exist before wiring buttons)
            var managerGO = new GameObject("Manager");
            var menu = managerGO.AddComponent<TitleMenu>();

            var btnLocal = SceneBuildersCommon.NewButton(canvas.transform, "BtnLocalCoop",
                new Vector2(0.5f, 0.5f), new Vector2(0f, 50f), new Vector2(360f, 80f),
                "Local Co-op");
            UnityEventTools.AddPersistentListener(btnLocal.onClick, new UnityAction(menu.OnLocalCoop));

            var btnOnline = SceneBuildersCommon.NewButton(canvas.transform, "BtnOnlineCoop",
                new Vector2(0.5f, 0.5f), new Vector2(0f, -50f), new Vector2(360f, 80f),
                "Online Co-op");
            UnityEventTools.AddPersistentListener(btnOnline.onClick, new UnityAction(menu.OnOnlineCoop));

            var btnSolo = SceneBuildersCommon.NewButton(canvas.transform, "BtnSoloAI",
                new Vector2(0.5f, 0.5f), new Vector2(0f, -150f), new Vector2(360f, 80f),
                "Solo vs AI");
            UnityEventTools.AddPersistentListener(btnSolo.onClick, new UnityAction(menu.OnSoloAI));

            var btnQuit = SceneBuildersCommon.NewButton(canvas.transform, "BtnQuit",
                new Vector2(0.5f, 0.5f), new Vector2(0f, -260f), new Vector2(360f, 60f),
                "Quit", 28f);
            UnityEventTools.AddPersistentListener(btnQuit.onClick, new UnityAction(menu.OnQuit));

            string scenePath = Path.Combine(SceneBuildersCommon.ScenesDir, "00_Title.unity");
            SceneBuildersCommon.SaveSceneAndRegister(scene, scenePath);
            Debug.Log($"[GRACE TitleSceneBuilder] Built {scenePath}.");
        }
    }
}
