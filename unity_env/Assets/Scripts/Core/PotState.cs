// PotState.cs
// Phase G1 (Core 3D game logic) for GRACE.
//
// Pure C# state machine for one Overcooked pot. Carroll uses a 20-tick cooking
// timer (8 Hz × 2.5s) once 3 onions are inside.

namespace Grace.Unity.Core
{
    /// <summary>
    /// What a chef is currently carrying.
    /// </summary>
    public enum HeldItem
    {
        None = 0,
        Onion = 1,
        Dish = 2,
        Soup = 3,
    }

    /// <summary>
    /// One pot's state. Mutable; <see cref="ChefSimulation"/> owns the lifetime
    /// and ticks all pots once per simulation step.
    /// </summary>
    public sealed class PotState
    {
        /// <summary>Maximum onions per pot (Carroll: 3).</summary>
        public const int MaxOnions = 3;

        /// <summary>
        /// How many ticks the pot needs to finish cooking once all onions are
        /// inside. Carroll: 20 ticks at 8 Hz ≈ 2.5 seconds.
        /// </summary>
        public const int CookingDuration = 20;

        /// <summary>Number of onions currently in the pot, 0..<see cref="MaxOnions"/>.</summary>
        public int OnionsIn;

        /// <summary>Ticks remaining until the soup is ready. 0 if not cooking.</summary>
        public int CookingTime;

        /// <summary>True once the cook timer has expired; the pot can be served.</summary>
        public bool IsReady;

        /// <summary>True while the cooking timer is counting down.</summary>
        public bool IsCooking => CookingTime > 0 && !IsReady;

        /// <summary>True iff no onions in the pot and not cooking / ready.</summary>
        public bool IsEmpty => OnionsIn == 0 && !IsCooking && !IsReady;

        /// <summary>
        /// Try to add an onion to the pot. Succeeds only when the pot is not
        /// already cooking, not ready, and not full. When the third onion lands
        /// the cook timer auto-starts (matches Carroll's old_dynamics path).
        /// </summary>
        public bool TryAddOnion()
        {
            if (IsReady || IsCooking) return false;
            if (OnionsIn >= MaxOnions) return false;
            OnionsIn++;
            if (OnionsIn == MaxOnions)
            {
                CookingTime = CookingDuration;
            }
            return true;
        }

        /// <summary>
        /// Try to serve a soup into <paramref name="newItem"/>. Succeeds only
        /// when the pot <see cref="IsReady"/>; on success the pot resets and
        /// <paramref name="newItem"/> is <see cref="HeldItem.Soup"/>. On failure
        /// <paramref name="newItem"/> is <see cref="HeldItem.None"/>.
        /// </summary>
        public bool TryServeTo(out HeldItem newItem)
        {
            if (!IsReady)
            {
                newItem = HeldItem.None;
                return false;
            }
            newItem = HeldItem.Soup;
            Reset();
            return true;
        }

        /// <summary>Advance the pot one simulation tick.</summary>
        public void Tick()
        {
            if (IsReady) return;
            if (CookingTime <= 0) return;
            CookingTime--;
            if (CookingTime == 0)
            {
                IsReady = true;
            }
        }

        /// <summary>Restore the pot to an empty starting state.</summary>
        public void Reset()
        {
            OnionsIn = 0;
            CookingTime = 0;
            IsReady = false;
        }
    }
}
