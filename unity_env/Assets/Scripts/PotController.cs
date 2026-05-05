// PotController.cs
// Phase 6 (Unity ML-Agents scaffolding) for GRACE.
// See DESIGN.md section 4.1.

using UnityEngine;

namespace GRACE.Unity
{
    /// <summary>
    /// Represents a single Overcooked-style soup pot. Tracks how many onions
    /// have been added, the cooking timer, and whether the soup is ready to be
    /// served by an agent holding a dish.
    /// </summary>
    public class PotController : MonoBehaviour
    {
        public const int MaxOnions = 3;

        [Tooltip("Number of onions currently in the pot (0..MaxOnions).")]
        public int OnionsIn;

        [Tooltip("Remaining ticks until the soup is ready while cooking.")]
        public int CookingTime;

        [Tooltip("How many ticks the pot needs to finish cooking once started.")]
        public int CookingDuration = 20;

        [Tooltip("True once cooking has completed and the pot can be served.")]
        public bool IsReady;

        /// <summary>True iff the pot has no onions and is not cooking / ready.</summary>
        public bool IsEmpty => OnionsIn == 0 && !IsCooking && !IsReady;

        /// <summary>True while the cooking timer is counting down.</summary>
        public bool IsCooking => CookingTime > 0 && !IsReady;

        /// <summary>
        /// Try to add an onion. Succeeds only if the pot is not yet full and
        /// has not started cooking. Once the pot reaches <see cref="MaxOnions"/>
        /// onions it automatically begins cooking.
        /// </summary>
        public bool TryAddOnion()
        {
            if (IsCooking || IsReady) return false;
            if (OnionsIn >= MaxOnions) return false;

            OnionsIn += 1;
            if (OnionsIn >= MaxOnions)
            {
                // Auto-start cooking when full.
                CookingTime = CookingDuration;
            }
            return true;
        }

        /// <summary>
        /// Attempt to serve a soup to <paramref name="agent"/>. The agent must
        /// be holding a dish (item id 2) and the pot must be ready. On success
        /// the agent ends up holding a soup (item id 3) and the pot is reset.
        /// </summary>
        public bool TryServe(ChefAgent agent)
        {
            if (agent == null) return false;
            if (!IsReady) return false;
            if (agent.HeldItem != ChefAgent.Item.Dish) return false;

            agent.HeldItem = ChefAgent.Item.Soup;
            Reset();
            return true;
        }

        /// <summary>Advance the pot one simulation tick.</summary>
        public void Tick()
        {
            if (IsReady) return;
            if (CookingTime <= 0) return;

            CookingTime -= 1;
            if (CookingTime <= 0)
            {
                CookingTime = 0;
                IsReady = true;
            }
        }

        /// <summary>Reset the pot to its empty starting state.</summary>
        public void Reset()
        {
            OnionsIn = 0;
            CookingTime = 0;
            IsReady = false;
        }
    }
}
