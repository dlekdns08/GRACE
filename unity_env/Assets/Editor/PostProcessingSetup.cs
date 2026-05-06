// PostProcessingSetup.cs
// Adds a Global Volume with Bloom + Vignette + ColorAdjustments to the open
// scene so the kitchen looks less flat. Run after opening 02_GameRoom.
//
// Tools → GRACE → Add Post-Processing to Current Scene

using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Grace.Unity.EditorTools
{
    public static class PostProcessingSetup
    {
        private const string ProfilePath = "Assets/Settings/GraceVolumeProfile.asset";

        [MenuItem("Tools/GRACE/Add Post-Processing to Current Scene")]
        public static void AddToCurrentScene()
        {
            var scene = EditorSceneManager.GetActiveScene();
            if (!scene.isLoaded)
            {
                EditorUtility.DisplayDialog("PostFX", "먼저 02_GameRoom 같은 씬을 여세요.", "OK");
                return;
            }

            // Build (or load) the volume profile asset.
            var profile = AssetDatabase.LoadAssetAtPath<UnityEngine.Rendering.VolumeProfile>(ProfilePath);
            if (profile == null)
            {
                profile = ScriptableObject.CreateInstance<UnityEngine.Rendering.VolumeProfile>();
                AssetDatabase.CreateAsset(profile, ProfilePath);
            }

            EnsureBloom(profile);
            EnsureVignette(profile);
            EnsureColorAdjustments(profile);
            EditorUtility.SetDirty(profile);

            // Find or create the volume in the scene.
            var existing = Object.FindFirstObjectByType<Volume>();
            Volume volume = existing;
            if (volume == null)
            {
                var go = new GameObject("PostProcessVolume");
                volume = go.AddComponent<Volume>();
                volume.isGlobal = true;
                volume.priority = 1;
            }
            volume.sharedProfile = profile;

            // Make sure the main camera renders post-processing.
            var cam = Camera.main;
            if (cam != null)
            {
                var data = cam.GetUniversalAdditionalCameraData();
                if (data != null) data.renderPostProcessing = true;
            }

            EditorSceneManager.MarkSceneDirty(scene);
            AssetDatabase.SaveAssets();
            EditorUtility.DisplayDialog("PostFX",
                "Bloom + Vignette + ColorAdjustments 추가됨.\nCtrl/Cmd-S로 씬 저장하세요.", "OK");
        }

        private static void EnsureBloom(UnityEngine.Rendering.VolumeProfile profile)
        {
            if (!profile.TryGet<Bloom>(out var bloom))
                bloom = profile.Add<Bloom>(true);
            bloom.intensity.overrideState = true;
            bloom.intensity.value = 0.45f;
            bloom.threshold.overrideState = true;
            bloom.threshold.value = 0.9f;
            bloom.scatter.overrideState = true;
            bloom.scatter.value = 0.7f;
            bloom.tint.overrideState = true;
            bloom.tint.value = new Color(1f, 0.96f, 0.85f);
        }

        private static void EnsureVignette(UnityEngine.Rendering.VolumeProfile profile)
        {
            if (!profile.TryGet<Vignette>(out var v))
                v = profile.Add<Vignette>(true);
            v.intensity.overrideState = true;
            v.intensity.value = 0.28f;
            v.smoothness.overrideState = true;
            v.smoothness.value = 0.4f;
            v.color.overrideState = true;
            v.color.value = new Color(0.05f, 0.04f, 0.04f);
        }

        private static void EnsureColorAdjustments(UnityEngine.Rendering.VolumeProfile profile)
        {
            if (!profile.TryGet<ColorAdjustments>(out var c))
                c = profile.Add<ColorAdjustments>(true);
            c.contrast.overrideState = true;
            c.contrast.value = 8f;
            c.saturation.overrideState = true;
            c.saturation.value = 12f;
            c.colorFilter.overrideState = true;
            c.colorFilter.value = new Color(1.0f, 0.97f, 0.92f);
        }
    }
}
