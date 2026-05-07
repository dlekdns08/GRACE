// SceneFeedbackSetup.cs
// One-click adder for the visual-feedback components in the open game scene:
//   - CounterItemRenderer on the Kitchen GameObject (so onions placed on
//     counters become visible)
//   - CustomerQueue near the serving counter (decorative cartoon customers
//     that bob and cheer when soups are served)
//
// Tools → GRACE → Add Visual Feedback to Current Scene

using Grace.Unity.Core;
using Grace.Unity.Network;
using Grace.Unity.Render;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Grace.Unity.EditorTools
{
    public static class SceneFeedbackSetup
    {
        [MenuItem("Tools/GRACE/Add Visual Feedback to Current Scene")]
        public static void Apply()
        {
            var scene = EditorSceneManager.GetActiveScene();
            if (!scene.isLoaded)
            {
                EditorUtility.DisplayDialog("Feedback", "먼저 02_GameRoom 씬을 여세요.", "OK");
                return;
            }

            var kitchenRoot = FindOrWarn<KitchenRenderer>("Kitchen / KitchenRenderer");
            if (kitchenRoot == null) return;

            // Counter-item renderer
            var counterRenderer = kitchenRoot.GetComponent<CounterItemRenderer>();
            if (counterRenderer == null)
                counterRenderer = kitchenRoot.gameObject.AddComponent<CounterItemRenderer>();
            counterRenderer.Kitchen = Object.FindFirstObjectByType<NetworkKitchen>();
            counterRenderer.TileSize = 1f;
            EditorUtility.SetDirty(counterRenderer);

            // Customer queue — placed on its own GameObject so it can be moved.
            var queueGO = GameObject.Find("CustomerQueue");
            if (queueGO == null)
            {
                queueGO = new GameObject("CustomerQueue");
                queueGO.transform.SetParent(null);
            }
            var queue = queueGO.GetComponent<CustomerQueue>();
            if (queue == null) queue = queueGO.AddComponent<CustomerQueue>();
            queue.Kitchen = Object.FindFirstObjectByType<NetworkKitchen>();

            // Try to anchor the queue near the serving counter automatically.
            var serving = FindServingCounterWorldPos(kitchenRoot);
            if (serving.HasValue)
            {
                Vector3 sp = serving.Value;
                queue.QueueOrigin = sp + new Vector3(1.6f, 0f, -0.2f);
                queue.QueueDirection = new Vector3(1f, 0f, 0f);
            }
            EditorUtility.SetDirty(queue);

            EditorSceneManager.MarkSceneDirty(scene);
            EditorUtility.DisplayDialog("Feedback",
                "추가됨:\n" +
                "• Kitchen → CounterItemRenderer (카운터에 놓인 양파/접시/수프 표시)\n" +
                "• CustomerQueue (서빙 카운터 옆 손님들, 서빙 시 환호)\n\n" +
                "Cmd-S로 씬 저장하세요.",
                "OK");
        }

        private static T FindOrWarn<T>(string label) where T : Component
        {
            var found = Object.FindFirstObjectByType<T>();
            if (found == null)
            {
                EditorUtility.DisplayDialog("Feedback",
                    $"{label}을(를) 씬에서 찾을 수 없습니다.\n02_GameRoom 매뉴얼대로 Kitchen GameObject를 먼저 만드세요.",
                    "OK");
            }
            return found;
        }

        private static Vector3? FindServingCounterWorldPos(KitchenRenderer kr)
        {
            // KitchenRenderer names spawned tiles "{TileKind}_{x}_{y}". After Build()
            // runs in Play mode the children exist; in Edit mode we may need to
            // estimate from the layout.
            for (int i = 0; i < kr.transform.childCount; i++)
            {
                var c = kr.transform.GetChild(i);
                if (c.name.StartsWith("ServingCounter_"))
                    return c.position;
            }
            // Edit-mode fallback: try the layout file directly.
            try
            {
                var layout = LayoutLoader.Load(kr.LayoutName);
                for (int x = 0; x < layout.Width; x++)
                    for (int y = 0; y < layout.Height; y++)
                        if (layout.At(new GridPos(x, y)) == TileKind.ServingCounter)
                            return new Vector3(x * kr.TileSize, 0f, -y * kr.TileSize);
            }
            catch { /* ignore */ }
            return null;
        }
    }
}
