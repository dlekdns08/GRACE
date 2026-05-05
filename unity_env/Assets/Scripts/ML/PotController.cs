// PotController.cs
// Phase G1: refactored to a thin scene-side MonoBehaviour mirror of
// Grace.Unity.Core.PotState. The Core simulation owns the authoritative pot
// state; this MonoBehaviour just exposes the same fields for inspector
// debugging, HUD reads, and back-compat with Phase 6 code that still
// references PotController.OnionsIn / IsReady / etc.

using UnityEngine;

namespace Grace.Unity.ML
{
    /// <summary>
    /// Visual / inspector mirror of one <see cref="Grace.Unity.Core.PotState"/>.
    /// Mutated by <see cref="KitchenEnvironment.Tick"/> after the simulation
    /// runs; not the source of truth.
    /// </summary>
    public class PotController : MonoBehaviour
    {
        public const int MaxOnions = Grace.Unity.Core.PotState.MaxOnions;

        [Tooltip("Number of onions currently in the pot (mirrored from ChefSimulation).")]
        public int OnionsIn;

        [Tooltip("Remaining ticks until the soup is ready (mirrored from ChefSimulation).")]
        public int CookingTime;

        [Tooltip("Cooking duration constant — informational only; authoritative value lives in PotState.")]
        public int CookingDuration = Grace.Unity.Core.PotState.CookingDuration;

        [Tooltip("True once cooking has completed (mirrored from ChefSimulation).")]
        public bool IsReady;

        public bool IsEmpty => OnionsIn == 0 && !IsCooking && !IsReady;
        public bool IsCooking => CookingTime > 0 && !IsReady;

        /// <summary>
        /// Reset the visual mirror to empty. Note: this DOES NOT reset the
        /// authoritative <see cref="Grace.Unity.Core.PotState"/>; that is
        /// handled by <see cref="KitchenEnvironment.ResetEpisode"/> via
        /// <see cref="Grace.Unity.Core.ChefSimulation.ResetEpisode"/>.
        /// </summary>
        public void Reset()
        {
            OnionsIn = 0;
            CookingTime = 0;
            IsReady = false;
        }
    }
}
