// KitchenSideChannelHook.cs
// Phase G1: moved to Grace.Unity.ML namespace. Logic unchanged from Phase 6.

using Unity.MLAgents;
using Unity.MLAgents.SideChannels;
using UnityEngine;

namespace Grace.Unity.ML
{
    /// <summary>
    /// Scene glue that registers the <see cref="StateSerializer"/> side
    /// channel on Awake and unregisters it on destruction. Drop this on a
    /// single manager GameObject in the Unity scene to enable text
    /// observations for the Python wrapper.
    /// </summary>
    public class KitchenSideChannelHook : MonoBehaviour
    {
        [Tooltip("Optional: serializer is auto-created if left null.")]
        public StateSerializer Serializer;

        [Tooltip("Optional: pushes textual state every Unity FixedUpdate when set.")]
        public KitchenEnvironment Kitchen;

        private bool _registered;

        private void Awake()
        {
            if (Serializer == null) Serializer = new StateSerializer();
            try
            {
                SideChannelManager.RegisterSideChannel(Serializer);
                _registered = true;
            }
            catch (System.Exception e)
            {
                Debug.LogWarning($"[GRACE] Failed to register state side channel: {e.Message}");
            }
        }

        private void OnDestroy()
        {
            if (!_registered || Serializer == null) return;
            try
            {
                SideChannelManager.UnregisterSideChannel(Serializer);
            }
            catch (System.Exception e)
            {
                Debug.LogWarning($"[GRACE] Failed to unregister state side channel: {e.Message}");
            }
            _registered = false;
        }
    }
}
