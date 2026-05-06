// AssetSwapper.cs
// Helper menus that let you replace the placeholder primitives with real
// FBX/GLB models you've imported into the project.
//
// Workflow:
//   1) Import the FBX into Assets/_Generated/ExternalModels/ (or anywhere).
//   2) Tools → GRACE → Swap Chef Mesh...   -> file dialog, pick the chef FBX.
//   3) Tools → GRACE → Swap Tile Mesh...   -> tile dropdown, pick the FBX.
//
// What it does: nests the chosen model under the existing prefab's "Visual"
// child so all gameplay scripts (NetworkObject, NetworkChefAgent, etc.) keep
// working. The original MeshFilter/MeshRenderer on the prefab root is
// disabled so the primitives don't render alongside the new model.

using System.IO;
using UnityEditor;
using UnityEngine;

namespace Grace.Unity.EditorTools
{
    public static class AssetSwapper
    {
        private const string GeneratedDir = "Assets/_Generated";
        private const string VisualChildName = "ExternalVisual";

        [MenuItem("Tools/GRACE/Swap Chef Mesh...")]
        public static void SwapChefMesh()
        {
            string path = EditorUtility.OpenFilePanel("Pick the chef FBX/Prefab", Application.dataPath, "fbx,prefab,obj");
            if (string.IsNullOrEmpty(path)) return;
            string assetPath = ToAssetPath(path);
            if (assetPath == null) return;

            var src = AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
            if (src == null) { EditorUtility.DisplayDialog("Swap", "선택한 파일이 GameObject 형태가 아닙니다.", "OK"); return; }

            ApplyModelTo($"{GeneratedDir}/NetworkChef.prefab", src, scaleHint: 0.9f);
        }

        [MenuItem("Tools/GRACE/Swap Tile Mesh...")]
        public static void SwapTileMesh()
        {
            int choice = EditorUtility.DisplayDialogComplex(
                "타일 선택",
                "어떤 타일에 새 모델을 적용할까요?",
                "OnionDispenser", "DishDispenser", "Pot");
            string tileName = choice switch
            {
                0 => "OnionDispenser",
                1 => "DishDispenser",
                2 => "Pot",
                _ => null,
            };
            if (tileName == null) return;

            string path = EditorUtility.OpenFilePanel($"Pick the {tileName} FBX/Prefab", Application.dataPath, "fbx,prefab,obj");
            if (string.IsNullOrEmpty(path)) return;
            string assetPath = ToAssetPath(path);
            if (assetPath == null) return;

            var src = AssetDatabase.LoadAssetAtPath<GameObject>(assetPath);
            if (src == null) { EditorUtility.DisplayDialog("Swap", "GameObject 로드 실패.", "OK"); return; }

            ApplyModelTo($"{GeneratedDir}/{tileName}.prefab", src, scaleHint: 1.0f);
        }

        [MenuItem("Tools/GRACE/Restore Primitive Visuals")]
        public static void RestorePrimitives()
        {
            // Removes any ExternalVisual child and re-enables the original capsule/cube renderer.
            foreach (var name in new[] {
                "NetworkChef", "OnionDispenser", "DishDispenser", "Pot",
                "ServingCounter", "Counter", "Floor", "Wall" })
            {
                string path = $"{GeneratedDir}/{name}.prefab";
                if (!File.Exists(path)) continue;
                var go = PrefabUtility.LoadPrefabContents(path);
                try
                {
                    var existing = go.transform.Find(VisualChildName);
                    if (existing != null) Object.DestroyImmediate(existing.gameObject, true);
                    var mf = go.GetComponent<MeshRenderer>();
                    if (mf != null) mf.enabled = true;
                    PrefabUtility.SaveAsPrefabAsset(go, path);
                }
                finally { PrefabUtility.UnloadPrefabContents(go); }
            }
            AssetDatabase.SaveAssets();
            EditorUtility.DisplayDialog("GRACE", "원래 프리미티브 비주얼로 복구했습니다.", "OK");
        }

        private static void ApplyModelTo(string prefabPath, GameObject sourceModel, float scaleHint)
        {
            var go = PrefabUtility.LoadPrefabContents(prefabPath);
            if (go == null) { EditorUtility.DisplayDialog("Swap", $"{prefabPath} 로드 실패.", "OK"); return; }
            try
            {
                // Remove previous external visual
                var existing = go.transform.Find(VisualChildName);
                if (existing != null) Object.DestroyImmediate(existing.gameObject, true);

                // Hide the placeholder capsule/cube renderer (keep collider/scripts intact).
                var rend = go.GetComponent<MeshRenderer>();
                if (rend != null) rend.enabled = false;

                // Instantiate the source model as a child.
                var instance = (GameObject)PrefabUtility.InstantiatePrefab(sourceModel);
                if (instance == null) instance = Object.Instantiate(sourceModel);
                instance.name = VisualChildName;
                instance.transform.SetParent(go.transform, false);
                instance.transform.localPosition = Vector3.zero;
                instance.transform.localScale = Vector3.one * scaleHint;

                PrefabUtility.SaveAsPrefabAsset(go, prefabPath);
                EditorUtility.DisplayDialog("Swap",
                    $"{prefabPath} 에 외부 모델을 적용했습니다.\n" +
                    "필요하면 ExternalVisual 자식의 Position/Scale/Rotation을 조정하세요.",
                    "OK");
            }
            finally { PrefabUtility.UnloadPrefabContents(go); }
        }

        private static string ToAssetPath(string fullPath)
        {
            fullPath = fullPath.Replace('\\', '/');
            string dataPath = Application.dataPath.Replace('\\', '/');
            if (!fullPath.StartsWith(dataPath))
            {
                EditorUtility.DisplayDialog("Swap",
                    "프로젝트의 Assets 폴더 안에 있는 파일만 선택할 수 있어요.\n" +
                    "FBX를 먼저 Assets/ 아래에 import하세요.",
                    "OK");
                return null;
            }
            return "Assets" + fullPath.Substring(dataPath.Length);
        }
    }
}
