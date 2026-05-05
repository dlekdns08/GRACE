// MovementInterpolator.cs
// Phase G2 (Render layer) for GRACE.
// See unity_env/GAME_DESIGN.md row 2 (hybrid movement: grid state + visual lerp).
//
// Smoothly lerps a transform from its previous world position to the world
// position of a target grid cell over a fixed duration (~150 ms). The internal
// simulation is unaffected — Carroll-faithful grid state lives in
// Grace.Unity.Core.ChefSimulation; this is purely visual.

using UnityEngine;

namespace Grace.Unity.Render
{
    /// <summary>Smooths grid-snapped chef movement into ~150 ms world-space lerps.</summary>
    public sealed class MovementInterpolator : MonoBehaviour
    {
        /// <summary>Duration (seconds) of one lerp from previous to new tile.</summary>
        public float lerpDuration = 0.15f;

        /// <summary>World units per grid cell.</summary>
        public float tileSize = 1.0f;

        private Vector3 _from;
        private Vector3 _to;
        private float _elapsed;
        private bool _interpolating;
        private bool _initialized;

        /// <summary>
        /// Convert a (gridX, gridY) cell to world coordinates.
        /// <b>y → -z</b> because Carroll's <c>y=0</c> is the TOP row, but Unity's
        /// world +z is forward (away from the camera in our top-down rig).
        /// </summary>
        public Vector3 GridToWorld(int x, int y) =>
            new Vector3(x * tileSize, 0f, -y * tileSize);

        /// <summary>
        /// Begin a lerp toward the world position of (gridX, gridY). No-op if
        /// already heading to the same target.
        /// </summary>
        public void SetTarget(int gridX, int gridY)
        {
            var newTo = GridToWorld(gridX, gridY);
            if (!_initialized)
            {
                _from = _to = newTo;
                transform.position = newTo;
                _initialized = true;
                _interpolating = false;
                return;
            }
            if (Vector3.SqrMagnitude(newTo - _to) < 1e-6f) return;

            _from = transform.position;
            _to = newTo;
            _elapsed = 0f;
            _interpolating = true;
        }

        /// <summary>Hard snap to a grid cell, clearing any in-flight interpolation.</summary>
        public void SnapTo(int gridX, int gridY)
        {
            _to = _from = GridToWorld(gridX, gridY);
            transform.position = _to;
            _interpolating = false;
            _initialized = true;
        }

        private void Update()
        {
            if (!_interpolating) return;
            _elapsed += Time.deltaTime;
            float t = Mathf.Clamp01(_elapsed / lerpDuration);
            // Smoothstep ease (3t^2 - 2t^3) — feels natural for grid step animation.
            t = t * t * (3f - 2f * t);
            transform.position = Vector3.Lerp(_from, _to, t);
            if (_elapsed >= lerpDuration)
            {
                transform.position = _to;
                _interpolating = false;
            }
        }
    }
}
