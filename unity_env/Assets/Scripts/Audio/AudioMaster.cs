// AudioMaster.cs
// Phase G3 (Audio layer) for GRACE.
//
// Singleton audio manager. Pools 8 AudioSources for SFX one-shots and owns one
// dedicated AudioSource for BGM. Public Play(SfxId) API, plus volume controls.

using System.Collections.Generic;
using UnityEngine;

namespace Grace.Unity.Audio
{
    /// <summary>Identifiers for in-game sound effects. Maps to AudioMaster.Entries.</summary>
    public enum SfxId
    {
        Footstep,
        Pickup,
        Drop,
        Interact,
        Serve,
        RoundStart,
        RoundEnd,
    }

    /// <summary>Singleton audio manager: pooled SFX one-shots + a single BGM AudioSource.</summary>
    public sealed class AudioMaster : MonoBehaviour
    {
        public static AudioMaster Instance { get; private set; }

        [System.Serializable]
        public class SfxEntry
        {
            public SfxId Id;
            public AudioClip[] Clips;
        }

        [Header("SFX bank")]
        public SfxEntry[] Entries;

        [Header("BGM")]
        public AudioSource Music;

        [Header("Mix")]
        [Range(0f, 1f)] public float MasterVolume = 1f;
        [Range(0f, 1f)] public float MusicVolume = 0.7f;
        [Range(0f, 1f)] public float SfxVolume = 1f;

        [Tooltip("Number of pooled AudioSources for one-shot SFX.")]
        public int PoolSize = 8;

        private Dictionary<SfxId, AudioClip[]> _map;
        private AudioSource[] _pool;
        private int _next;

        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);

            _map = new Dictionary<SfxId, AudioClip[]>();
            if (Entries != null)
            {
                foreach (var e in Entries)
                {
                    if (e == null || e.Clips == null) continue;
                    _map[e.Id] = e.Clips;
                }
            }

            _pool = new AudioSource[Mathf.Max(1, PoolSize)];
            for (int i = 0; i < _pool.Length; i++)
            {
                var src = gameObject.AddComponent<AudioSource>();
                src.playOnAwake = false;
                src.loop = false;
                src.spatialBlend = 0f;
                _pool[i] = src;
            }

            ApplyMusicVolume();
        }

        /// <summary>Play one of the clips for <paramref name="id"/> (random pick if multiple).</summary>
        public void Play(SfxId id)
        {
            if (_map == null || !_map.TryGetValue(id, out var clips)) return;
            if (clips == null || clips.Length == 0) return;
            var clip = clips[Random.Range(0, clips.Length)];
            if (clip == null) return;
            var src = _pool[_next];
            _next = (_next + 1) % _pool.Length;
            src.PlayOneShot(clip, MasterVolume * SfxVolume);
        }

        /// <summary>Update mix levels at runtime (e.g. from a settings menu).</summary>
        public void SetVolumes(float master, float music, float sfx)
        {
            MasterVolume = Mathf.Clamp01(master);
            MusicVolume = Mathf.Clamp01(music);
            SfxVolume = Mathf.Clamp01(sfx);
            ApplyMusicVolume();
        }

        private void ApplyMusicVolume()
        {
            if (Music != null) Music.volume = MasterVolume * MusicVolume;
        }
    }
}
