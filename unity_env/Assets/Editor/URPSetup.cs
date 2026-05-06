// URPSetup.cs
// One-click bootstrap for Universal Render Pipeline.
//
// Creates Assets/Settings/URP-HighFidelity.asset (UniversalRenderPipelineAsset)
// + a UniversalRendererData sidecar, then assigns the asset to
// GraphicsSettings.defaultRenderPipeline and every QualitySettings level.
// Run via Tools → GRACE → Setup URP Pipeline.

using System.IO;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Grace.Unity.EditorTools
{
    public static class URPSetup
    {
        private const string SettingsDir = "Assets/Settings";
        private const string UrpAssetPath = "Assets/Settings/URP-HighFidelity.asset";
        private const string RendererPath = "Assets/Settings/URP-HighFidelity_Renderer.asset";

        [MenuItem("Tools/GRACE/Setup URP Pipeline")]
        public static void Setup()
        {
            if (!Directory.Exists(SettingsDir))
            {
                Directory.CreateDirectory(SettingsDir);
                AssetDatabase.Refresh();
            }

            var rendererData = AssetDatabase.LoadAssetAtPath<UniversalRendererData>(RendererPath);
            if (rendererData == null)
            {
                rendererData = ScriptableObject.CreateInstance<UniversalRendererData>();
                AssetDatabase.CreateAsset(rendererData, RendererPath);
            }

            var urpAsset = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(UrpAssetPath);
            if (urpAsset == null)
            {
                urpAsset = ScriptableObject.CreateInstance<UniversalRenderPipelineAsset>();
                AssetDatabase.CreateAsset(urpAsset, UrpAssetPath);
            }

            var so = new SerializedObject(urpAsset);
            var rendererList = so.FindProperty("m_RendererDataList");
            if (rendererList != null)
            {
                rendererList.arraySize = 1;
                rendererList.GetArrayElementAtIndex(0).objectReferenceValue = rendererData;
            }
            var defaultIdx = so.FindProperty("m_DefaultRendererIndex");
            if (defaultIdx != null) defaultIdx.intValue = 0;
            so.ApplyModifiedPropertiesWithoutUndo();

            GraphicsSettings.defaultRenderPipeline = urpAsset;

            int originalLevel = QualitySettings.GetQualityLevel();
            int levelCount = QualitySettings.names.Length;
            for (int i = 0; i < levelCount; i++)
            {
                QualitySettings.SetQualityLevel(i, false);
                QualitySettings.renderPipeline = urpAsset;
            }
            QualitySettings.SetQualityLevel(originalLevel, false);

            EditorUtility.SetDirty(urpAsset);
            EditorUtility.SetDirty(rendererData);
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();

            Debug.Log($"[GRACE URPSetup] Created {UrpAssetPath} and assigned it to GraphicsSettings + all QualitySettings levels.");
        }
    }
}
