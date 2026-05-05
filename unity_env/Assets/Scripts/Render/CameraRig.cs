// CameraRig.cs
// Phase G2 (Render layer) for GRACE.
// See unity_env/GAME_DESIGN.md row 1 (semi-isometric 30° tilted top-down view).
//
// Auto-frames the kitchen below the camera, tilted 30° from vertical so the
// player sees a semi-isometric top-down view. Distance scales with kitchen size.

using Grace.Unity.Core;
using UnityEngine;

namespace Grace.Unity.Render
{
    /// <summary>Positions the camera in a 30° tilted top-down rig framing the whole kitchen.</summary>
    [RequireComponent(typeof(Camera))]
    public sealed class CameraRig : MonoBehaviour
    {
        [Header("Rig")]
        [Tooltip("Tilt from straight-down toward +z, in degrees. 0 = orthogonal top-down, 30 = our default.")]
        public float Tilt = 30f;

        [Tooltip("Minimum camera-to-center distance, in world units.")]
        public float MinDistance = 8f;

        [Tooltip("Distance increment per max(width,height) tile of layout.")]
        public float DistancePerTile = 1.4f;

        [Header("Target")]
        public KitchenRenderer Kitchen;

        private void Start() => FrameKitchen();

        /// <summary>Recompute camera position/rotation to fit the current kitchen.</summary>
        public void FrameKitchen()
        {
            if (Kitchen == null) Kitchen = FindFirstObjectByType<KitchenRenderer>();

            float w = 7f;
            float h = 5f;
            if (Kitchen != null && Kitchen.CurrentLayout != null)
            {
                w = Kitchen.CurrentLayout.Width * Kitchen.TileSize;
                h = Kitchen.CurrentLayout.Height * Kitchen.TileSize;
            }

            // Layout center in world space (mirroring KitchenRenderer's y → -z mapping).
            var center = new Vector3(w * 0.5f, 0f, -h * 0.5f);

            float dist = Mathf.Max(MinDistance, DistancePerTile * Mathf.Max(w, h));
            float tiltRad = Mathf.Deg2Rad * Tilt;

            // Camera sits above and behind the center (smaller z), looking
            // forward+down toward it. With Tilt=30°, the view is semi-isometric.
            var offset = new Vector3(0f,
                                     dist * Mathf.Cos(tiltRad),
                                     -dist * Mathf.Sin(tiltRad));
            transform.position = center + offset;
            transform.LookAt(center);
        }
    }
}
