// SceneBuildersCommon.cs
// Shared helpers for the title / lobby / round-end scene builders.

using TMPro;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace Grace.Unity.EditorTools
{
    internal static class SceneBuildersCommon
    {
        public const string ScenesDir = "Assets/Scenes";

        public static Scene NewSingleScene(string name)
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            scene.name = name;
            return scene;
        }

        public static void SaveSceneAndRegister(Scene scene, string scenePath)
        {
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, scenePath);

            EditorBuildSettingsScene[] existing = EditorBuildSettings.scenes;
            foreach (var s in existing) if (s.path == scenePath) return;
            var list = new System.Collections.Generic.List<EditorBuildSettingsScene>(existing)
            {
                new EditorBuildSettingsScene(scenePath, true),
            };
            EditorBuildSettings.scenes = list.ToArray();
        }

        public static GameObject NewUiCamera()
        {
            var go = new GameObject("MainCamera");
            go.tag = "MainCamera";
            var cam = go.AddComponent<Camera>();
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = new Color(0.106f, 0.122f, 0.165f); // #1B1F2A
            cam.orthographic = true;
            cam.orthographicSize = 5f;
            go.transform.position = new Vector3(0f, 1f, -10f);
            go.AddComponent<AudioListener>();
            return go;
        }

        public static GameObject EnsureEventSystem()
        {
            var existing = Object.FindFirstObjectByType<EventSystem>();
            if (existing != null) return existing.gameObject;
            return new GameObject("EventSystem", typeof(EventSystem), typeof(StandaloneInputModule));
        }

        public static GameObject NewCanvas(string name)
        {
            var go = new GameObject(name,
                typeof(RectTransform), typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
            var canvas = go.GetComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            var scaler = go.GetComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1920f, 1080f);
            scaler.matchWidthOrHeight = 0.5f;
            return go;
        }

        public static TMP_Text NewText(
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
            text.textWrappingMode = TextWrappingModes.NoWrap;
            text.raycastTarget = false;
            return text;
        }

        public static Button NewButton(
            Transform parent, string name,
            Vector2 anchor, Vector2 anchoredPos, Vector2 size,
            string label, float fontSize = 32f)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(Image), typeof(Button));
            go.transform.SetParent(parent, false);
            var rt = go.GetComponent<RectTransform>();
            rt.anchorMin = rt.anchorMax = anchor;
            rt.pivot = new Vector2(0.5f, 0.5f);
            rt.anchoredPosition = anchoredPos;
            rt.sizeDelta = size;

            var img = go.GetComponent<Image>();
            img.color = new Color(0.2f, 0.25f, 0.32f, 1f);

            var btn = go.GetComponent<Button>();
            var colors = btn.colors;
            colors.highlightedColor = new Color(0.3f, 0.4f, 0.55f, 1f);
            colors.pressedColor = new Color(0.15f, 0.2f, 0.27f, 1f);
            btn.colors = colors;

            var labelGO = new GameObject("Text (TMP)", typeof(RectTransform));
            labelGO.transform.SetParent(go.transform, false);
            var lrt = labelGO.GetComponent<RectTransform>();
            lrt.anchorMin = Vector2.zero;
            lrt.anchorMax = Vector2.one;
            lrt.offsetMin = Vector2.zero;
            lrt.offsetMax = Vector2.zero;
            var tmp = labelGO.AddComponent<TextMeshProUGUI>();
            tmp.text = label;
            tmp.fontSize = fontSize;
            tmp.alignment = TextAlignmentOptions.Center;
            tmp.color = Color.white;
            tmp.raycastTarget = false;

            return btn;
        }

        public static TMP_InputField NewInputField(
            Transform parent, string name,
            Vector2 anchor, Vector2 anchoredPos, Vector2 size,
            string placeholder)
        {
            var go = new GameObject(name, typeof(RectTransform), typeof(Image));
            go.transform.SetParent(parent, false);
            var rt = go.GetComponent<RectTransform>();
            rt.anchorMin = rt.anchorMax = anchor;
            rt.pivot = new Vector2(0.5f, 0.5f);
            rt.anchoredPosition = anchoredPos;
            rt.sizeDelta = size;

            var img = go.GetComponent<Image>();
            img.color = new Color(0.13f, 0.15f, 0.20f, 1f);

            var textArea = new GameObject("Text Area", typeof(RectTransform), typeof(RectMask2D));
            textArea.transform.SetParent(go.transform, false);
            var tarRT = textArea.GetComponent<RectTransform>();
            tarRT.anchorMin = Vector2.zero;
            tarRT.anchorMax = Vector2.one;
            tarRT.offsetMin = new Vector2(10, 6);
            tarRT.offsetMax = new Vector2(-10, -6);

            var placeholderGO = new GameObject("Placeholder", typeof(RectTransform));
            placeholderGO.transform.SetParent(textArea.transform, false);
            var pRT = placeholderGO.GetComponent<RectTransform>();
            pRT.anchorMin = Vector2.zero;
            pRT.anchorMax = Vector2.one;
            pRT.offsetMin = pRT.offsetMax = Vector2.zero;
            var pTmp = placeholderGO.AddComponent<TextMeshProUGUI>();
            pTmp.text = placeholder;
            pTmp.fontSize = 28;
            pTmp.color = new Color(1f, 1f, 1f, 0.4f);
            pTmp.alignment = TextAlignmentOptions.MidlineLeft;

            var textGO = new GameObject("Text", typeof(RectTransform));
            textGO.transform.SetParent(textArea.transform, false);
            var tRT = textGO.GetComponent<RectTransform>();
            tRT.anchorMin = Vector2.zero;
            tRT.anchorMax = Vector2.one;
            tRT.offsetMin = tRT.offsetMax = Vector2.zero;
            var tTmp = textGO.AddComponent<TextMeshProUGUI>();
            tTmp.text = "";
            tTmp.fontSize = 28;
            tTmp.color = Color.white;
            tTmp.alignment = TextAlignmentOptions.MidlineLeft;

            var input = go.AddComponent<TMP_InputField>();
            input.textViewport = tarRT;
            input.textComponent = tTmp;
            input.placeholder = pTmp;
            input.characterLimit = 8;

            return input;
        }
    }
}
