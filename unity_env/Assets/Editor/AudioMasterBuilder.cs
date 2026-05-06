// AudioMasterBuilder.cs
// Adds an AudioMaster GameObject to the current scene with one entry per
// SfxId enum value (clip arrays empty — drop in real clips later) and a
// dedicated child AudioSource for BGM. Run via
// Tools → GRACE → Add AudioMaster to Current Scene.

using System;
using Grace.Unity.Audio;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;

namespace Grace.Unity.EditorTools
{
    public static class AudioMasterBuilder
    {
        [MenuItem("Tools/GRACE/Add AudioMaster to Current Scene")]
        public static void AddAudioMaster()
        {
            var existing = UnityEngine.Object.FindFirstObjectByType<AudioMaster>();
            if (existing != null)
            {
                Debug.LogWarning($"[GRACE AudioMasterBuilder] AudioMaster already exists ({existing.gameObject.name}). Aborting.");
                Selection.activeGameObject = existing.gameObject;
                return;
            }

            var go = new GameObject("AudioMaster");
            var master = go.AddComponent<AudioMaster>();

            var sfxIds = (SfxId[])Enum.GetValues(typeof(SfxId));
            master.Entries = new AudioMaster.SfxEntry[sfxIds.Length];
            for (int i = 0; i < sfxIds.Length; i++)
            {
                master.Entries[i] = new AudioMaster.SfxEntry
                {
                    Id = sfxIds[i],
                    Clips = Array.Empty<AudioClip>(),
                };
            }

            var bgmGO = new GameObject("BGM");
            bgmGO.transform.SetParent(go.transform, false);
            var bgmSrc = bgmGO.AddComponent<AudioSource>();
            bgmSrc.playOnAwake = true;
            bgmSrc.loop = true;
            bgmSrc.spatialBlend = 0f;
            bgmSrc.volume = 0.7f;
            master.Music = bgmSrc;

            master.MasterVolume = 1f;
            master.MusicVolume = 0.7f;
            master.SfxVolume = 1f;
            master.PoolSize = 8;

            Undo.RegisterCreatedObjectUndo(go, "Add AudioMaster");
            EditorSceneManager.MarkSceneDirty(go.scene);
            Selection.activeGameObject = go;

            Debug.Log("[GRACE AudioMasterBuilder] AudioMaster added with stub Entries (one per SfxId). Drop AudioClips into each entry's Clips array.");
        }
    }
}
