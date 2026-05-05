// KitchenEnvironment.cs
// Phase 6 (Unity ML-Agents scaffolding) for GRACE.
// See DESIGN.md section 4.1.

using System.Collections.Generic;
using UnityEngine;

namespace GRACE.Unity
{
    /// <summary>
    /// Owns the simulation state for a single Overcooked episode: agents,
    /// pots, score, step counter. Driven externally (no Update loop) so
    /// ML-Agents can step it deterministically per decision.
    /// </summary>
    public class KitchenEnvironment : MonoBehaviour
    {
        [Header("Episode")]
        public int Step;
        public int MaxSteps = 400;
        public int Score;
        public int SoupsServed;

        [Header("Layout (cramped_room default)")]
        public int LayoutWidth = 5;
        public int LayoutHeight = 5;

        [Header("Scene Refs (filled in inspector)")]
        public List<ChefAgent> Agents = new List<ChefAgent>();
        public List<PotController> Pots = new List<PotController>();

        /// <summary>Reward delivered to whichever agent serves a soup.</summary>
        public const float SoupReward = 20f;

        /// <summary>Target soups per episode; reaching it ends the episode.</summary>
        public const int TargetSoups = 5;

        // Per-agent reward accumulator. Cleared each Tick() so ChefAgent can
        // pull the reward delta and forward it to ML-Agents via AddReward().
        private readonly Dictionary<ChefAgent, float> _pendingRewards =
            new Dictionary<ChefAgent, float>();

        /// <summary>Reset all per-episode state to defaults.</summary>
        public void ResetEpisode()
        {
            Step = 0;
            Score = 0;
            SoupsServed = 0;
            _pendingRewards.Clear();

            for (int i = 0; i < Pots.Count; i++)
            {
                if (Pots[i] != null) Pots[i].Reset();
            }

            for (int i = 0; i < Agents.Count; i++)
            {
                var a = Agents[i];
                if (a == null) continue;
                a.HeldItem = ChefAgent.Item.None;
                // Place agents on a simple deterministic spawn line.
                int x = i % Mathf.Max(1, LayoutWidth);
                int y = i / Mathf.Max(1, LayoutWidth);
                a.GridX = x;
                a.GridY = y;
                a.transform.localPosition = new Vector3(x, 0f, y);
            }
        }

        /// <summary>
        /// Advance the simulation by one tick. Increments the step counter,
        /// progresses pot cooking, and resets per-agent reward accumulators
        /// (the rewards themselves are added at action time inside ChefAgent).
        /// </summary>
        public void Tick()
        {
            Step += 1;
            for (int i = 0; i < Pots.Count; i++)
            {
                if (Pots[i] != null) Pots[i].Tick();
            }
        }

        /// <summary>Returns true when the episode should terminate.</summary>
        public bool IsDone()
        {
            return Step >= MaxSteps || SoupsServed >= TargetSoups;
        }

        /// <summary>
        /// Called by <see cref="PotController.TryServe"/> indirectly, or by
        /// <see cref="ChefAgent"/> when it delivers a soup. Awards score and
        /// reward for the serving agent.
        /// </summary>
        public void RegisterSoupDelivery(ChefAgent server)
        {
            SoupsServed += 1;
            Score += (int)SoupReward;
            AddReward(server, SoupReward);
        }

        /// <summary>Queue a reward delta for <paramref name="agent"/>.</summary>
        public void AddReward(ChefAgent agent, float delta)
        {
            if (agent == null) return;
            if (!_pendingRewards.TryGetValue(agent, out float current)) current = 0f;
            _pendingRewards[agent] = current + delta;
        }

        /// <summary>Pop and return the pending reward for <paramref name="agent"/>.</summary>
        public float ConsumeReward(ChefAgent agent)
        {
            if (agent == null) return 0f;
            if (!_pendingRewards.TryGetValue(agent, out float r)) return 0f;
            _pendingRewards[agent] = 0f;
            return r;
        }

        /// <summary>Find the pot at grid <paramref name="x"/>,<paramref name="y"/> if any.</summary>
        public PotController PotAt(int x, int y)
        {
            for (int i = 0; i < Pots.Count; i++)
            {
                var p = Pots[i];
                if (p == null) continue;
                var lp = p.transform.localPosition;
                if (Mathf.RoundToInt(lp.x) == x && Mathf.RoundToInt(lp.z) == y) return p;
            }
            return null;
        }

        /// <summary>Whether (<paramref name="x"/>,<paramref name="y"/>) is inside the layout.</summary>
        public bool InBounds(int x, int y)
        {
            return x >= 0 && x < LayoutWidth && y >= 0 && y < LayoutHeight;
        }
    }
}
