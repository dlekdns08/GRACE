// HUDBuilder.cs
// One-click HUD scaffolding for the active scene.
//
// Creates HUDCanvas (Screen Space Overlay, 1920x1080 reference) with 6 TMP
// text fields wired into Grace.Unity.UI.HUD, plus an EventSystem if missing.
// Also wires the HUD's Kitchen reference to whatever NetworkKitchen exists in
// the scene (Kitchen GameObject, per the KitchenSceneBuilder layout).
//
// Run via Tools → GRACE → Add HUD to Current Scene.

using Grace.Unity.Network;
using Grace.Unity.UI;
using TMPro;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Grace.Unity.EditorTools
{
    public static class HUDBuilder
    {
        [MenuItem("Tools/GRACE/Add HUD to Current Scene")]
        public static void AddHud()
        {
            var existing = Object.FindFirstObjectByType<HUD>();
            if (existing != null)
            {
                Debug.LogWarning($"[GRACE HUDBuilder] HUD already exists at {existing.gameObject.name}. Aborting to avoid duplicates.");
                Selection.activeGameObject = existing.gameObject;
                return;
            }

            // Canvas root
            var canvasGO = new GameObject("HUDCanvas",
                typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            var canvas = canvasGO.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 100;
            var scaler = canvasGO.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920f, 1080f);
            scaler.matchWidthOrHeight = 0.5f;

            // EventSystem (only one allowed per scene)
            if (Object.FindFirstObjectByType<EventSystem>() == null)
            {
                var esGO = new GameObject("EventSystem", typeof(EventSystem), typeof(StandaloneInputModule));
                Undo.RegisterCreatedObjectUndo(esGO, "Add HUD");
            }

            // Six TMP texts
            var timer = MakeText(canvasGO.transform, "TimerText",
                new Vector2(0.5f, 1f), new Vector2(0.5f, 1f),
                new Vector2(0f, -40f), new Vector2(400f, 80f),
                "50.0s", 64, TextAlignmentOptions.Center);

            var score = MakeText(canvasGO.transform, "ScoreText",
                new Vector2(0f, 1f), new Vector2(0f, 1f),
                new Vector2(120f, -40f), new Vector2(360f, 50f),
                "Score: 0", 36, TextAlignmentOptions.Left);

            var soups = MakeText(canvasGO.transform, "SoupsText",
                new Vector2(0f, 1f), new Vector2(0f, 1f),
                new Vector2(120f, -90f), new Vector2(360f, 40f),
                "Soups: 0", 28, TextAlignmentOptions.Left);

            var pots = MakeText(canvasGO.transform, "PotsText",
                new Vector2(1f, 1f), new Vector2(1f, 1f),
                new Vector2(-120f, -40f), new Vector2(500f, 60f),
                "Pot0: empty", 28, TextAlignmentOptions.Right);

            var p1 = MakeText(canvasGO.transform, "Player1HeldText",
                new Vector2(0f, 0f), new Vector2(0f, 0f),
                new Vector2(120f, 60f), new Vector2(360f, 50f),
                "P1: —", 32, TextAlignmentOptions.Left);

            var p2 = MakeText(canvasGO.transform, "Player2HeldText",
                new Vector2(1f, 0f), new Vector2(1f, 0f),
                new Vector2(-120f, 60f), new Vector2(360f, 50f),
                "P2: —", 32, TextAlignmentOptions.Right);

            // HUD component
            var hud = canvasGO.AddComponent<HUD>();
            hud.TimerText = timer;
            hud.ScoreText = score;
            hud.SoupsText = soups;
            hud.PotsText = pots;
            hud.Player1HeldText = p1;
            hud.Player2HeldText = p2;
            hud.TicksPerSecond = 8f;

            var netKitchen = Object.FindFirstObjectByType<NetworkKitchen>();
            if (netKitchen != null)
            {
                hud.Kitchen = netKitchen;
                Debug.Log($"[GRACE HUDBuilder] Wired HUD.Kitchen → {netKitchen.gameObject.name}.");
            }
            else
            {
                Debug.LogWarning("[GRACE HUDBuilder] No NetworkKitchen in scene. Wire HUD.Kitchen or HUD.OfflineSim manually.");
            }

            Undo.RegisterCreatedObjectUndo(canvasGO, "Add HUD");
            EditorSceneManager.MarkSceneDirty(canvasGO.scene);
            Selection.activeGameObject = canvasGO;

            Debug.Log("[GRACE HUDBuilder] HUDCanvas created. Save the scene with Cmd-S.");
        }

        private static TMP_Text MakeText(
            Transform parent, string name,
            Vector2 anchorMin, Vector2 anchorMax,
            Vector2 anchoredPos, Vector2 size,
            string content, float fontSize, TextAlignmentOptions align)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var rt = go.GetComponent<RectTransform>();
            rt.anchorMin = anchorMin;
            rt.anchorMax = anchorMax;
            rt.pivot = new Vector2((anchorMin.x + anchorMax.x) * 0.5f, (anchorMin.y + anchorMax.y) * 0.5f);
            rt.anchoredPosition = anchoredPos;
            rt.sizeDelta = size;

            var text = go.AddComponent<TextMeshProUGUI>();
            text.text = content;
            text.fontSize = fontSize;
            text.alignment = align;
            text.color = Color.white;
            text.enableWordWrapping = false;
            text.raycastTarget = false;
            text.outlineWidth = 0.2f;
            text.outlineColor = new Color32(0, 0, 0, 200);
            return text;
        }
    }
}
