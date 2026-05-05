// KitchenEnvironment.cs
// Phase G1: refactored to delegate all game-state logic to
// Grace.Unity.Core.ChefSimulation. This MonoBehaviour is now a thin
// scene-binding wrapper that:
//   1. Loads a layout (from Resources/Layouts/{LayoutName}.txt) on Awake.
//   2. Builds a ChefSimulation from it.
//   3. Provides ML-Agents-friendly accessors (Agents list, Pots list,
//      RegisterSoupDelivery, AddReward / ConsumeReward) used by ChefAgent.
//
// All actual mutation of the game world goes through ChefSimulation.Tick,
// which is called once per simulation step from KitchenEnvironment.Tick.

using System.Collections.Generic;
using Grace.Unity.Core;
using UnityEngine;

namespace Grace.Unity.ML
{
    /// <summary>
    /// Scene-bound wrapper around <see cref="ChefSimulation"/>. ML-Agents
    /// agents (<see cref="ChefAgent"/>) talk to this; this class talks to the
    /// pure-C# simulation.
    /// </summary>
    public class KitchenEnvironment : MonoBehaviour
    {
        [Header("Layout")]
        [Tooltip("Layout name to load from Assets/Resources/Layouts/{LayoutName}.txt")]
        public string LayoutName = "cramped_room";

        [Header("Episode")]
        public int MaxSteps = 400;

        /// <summary>Score reward per soup delivered (Carroll: 20).</summary>
        public const float SoupReward = ChefSimulation.RewardServe;

        /// <summary>Target soups per episode for early termination. 0 disables (Carroll-faithful).</summary>
        public const int TargetSoups = 0;

        [Header("Scene Refs (filled in inspector)")]
        public List<ChefAgent> Agents = new List<ChefAgent>();

        // PotControllers are now optional render-side mirrors; the authoritative
        // pot state lives inside ChefSimulation.Pots.
        public List<PotController> Pots = new List<PotController>();

        // ----- exposed simulation state (read-only mirrors) ------------------

        public int Step => _simulation != null ? _simulation.Step : 0;
        public int Score => _simulation != null ? _simulation.Score : 0;
        public int SoupsServed => _simulation != null ? _simulation.SoupsServed : 0;
        public int LayoutWidth => _simulation != null ? _simulation.Layout.Width : 0;
        public int LayoutHeight => _simulation != null ? _simulation.Layout.Height : 0;

        /// <summary>The Core simulation. Null until <see cref="EnsureSimulation"/> runs.</summary>
        public ChefSimulation Simulation => _simulation;

        // ----- private state -------------------------------------------------

        private ChefSimulation _simulation;
        private bool _initialised;

        // Per-agent reward queue. ChefAgent pulls from this in OnActionReceived.
        private readonly Dictionary<ChefAgent, float> _pendingRewards =
            new Dictionary<ChefAgent, float>();

        // Joint action buffer rebuilt every Tick. Index = Agents index.
        private int[] _jointActionBuf;

        // ---------------------------------------------------------------------
        // Lifecycle
        // ---------------------------------------------------------------------

        private void Awake()
        {
            EnsureSimulation();
        }

        /// <summary>
        /// Lazily build the simulation if it's not yet ready. Safe to call
        /// multiple times.
        /// </summary>
        public void EnsureSimulation()
        {
            if (_initialised) return;
            try
            {
                var ta = Resources.Load<TextAsset>("Layouts/" + LayoutName);
                KitchenLayout layout;
                if (ta != null)
                {
                    layout = LayoutLoader.LoadFromString(ta.text, LayoutName);
                }
                else
                {
                    Debug.LogWarning(
                        $"[GRACE] Resources/Layouts/{LayoutName}.txt not found; falling back to filesystem LayoutLoader.Load.");
                    layout = LayoutLoader.Load(LayoutName);
                }
                _simulation = new ChefSimulation(layout, MaxSteps);
                _initialised = true;
            }
            catch (System.Exception e)
            {
                Debug.LogError($"[GRACE] Failed to load layout '{LayoutName}': {e.Message}");
            }
        }

        // ---------------------------------------------------------------------
        // Episode control
        // ---------------------------------------------------------------------

        /// <summary>Reset all per-episode state to defaults.</summary>
        public void ResetEpisode()
        {
            EnsureSimulation();
            if (_simulation == null) return;

            _simulation.MaxSteps = MaxSteps;
            _simulation.ResetEpisode();
            _pendingRewards.Clear();

            // Sync MonoBehaviour mirrors.
            for (int i = 0; i < Agents.Count; i++)
            {
                var a = Agents[i];
                if (a == null) continue;
                if (i < _simulation.Chefs.Count)
                {
                    var s = _simulation.Chefs[i];
                    a.GridX = s.Position.X;
                    a.GridY = s.Position.Y;
                    a.HeldItem = (ChefAgent.Item)(int)s.Held;
                    a.transform.localPosition = new Vector3(s.Position.X, 0f, s.Position.Y);
                }
            }
            for (int i = 0; i < Pots.Count; i++)
            {
                if (Pots[i] != null) Pots[i].Reset();
            }
        }

        /// <summary>Returns true when the episode should terminate.</summary>
        public bool IsDone()
        {
            if (_simulation == null) return false;
            if (_simulation.IsDone()) return true;
            return TargetSoups > 0 && _simulation.SoupsServed >= TargetSoups;
        }

        // ---------------------------------------------------------------------
        // Tick (single source of truth)
        // ---------------------------------------------------------------------

        /// <summary>
        /// Apply <paramref name="jointActions"/> (one int per Agent in
        /// <see cref="Agents"/> list order) and advance simulation by one tick.
        /// Returns the reward delta this tick. Carroll's reward is shared, so
        /// it's distributed equally across all agents via the per-agent queue.
        /// </summary>
        public int Tick(int[] jointActions)
        {
            EnsureSimulation();
            if (_simulation == null) return 0;

            int reward = _simulation.Tick(jointActions);

            // Mirror state back to MonoBehaviour wrappers so other code (HUD,
            // recorder, ML observations) reads it normally.
            for (int i = 0; i < Agents.Count && i < _simulation.Chefs.Count; i++)
            {
                var a = Agents[i];
                if (a == null) continue;
                var s = _simulation.Chefs[i];
                a.GridX = s.Position.X;
                a.GridY = s.Position.Y;
                a.HeldItem = (ChefAgent.Item)(int)s.Held;
                a.transform.localPosition = new Vector3(s.Position.X, 0f, s.Position.Y);
            }

            // Mirror pots (best-effort: pot at the same grid position).
            foreach (var kv in _simulation.Pots)
            {
                var pot = FindPotAt(kv.Key.X, kv.Key.Y);
                if (pot != null)
                {
                    pot.OnionsIn = kv.Value.OnionsIn;
                    pot.CookingTime = kv.Value.CookingTime;
                    pot.IsReady = kv.Value.IsReady;
                }
            }

            // Distribute reward equally to all agents (Carroll: shared reward).
            if (reward != 0 && Agents.Count > 0)
            {
                float per = (float)reward / Agents.Count;
                for (int i = 0; i < Agents.Count; i++)
                {
                    AddReward(Agents[i], per);
                }
            }

            return reward;
        }

        /// <summary>
        /// Convenience: build a joint-action vector from each agent's most
        /// recent <see cref="ChefAgent.LastAction"/> and tick once. Used by
        /// <see cref="HumanPlayDriver"/>.
        /// </summary>
        public int TickFromAgentLastActions()
        {
            EnsureSimulation();
            if (_simulation == null) return 0;
            if (_jointActionBuf == null || _jointActionBuf.Length != Agents.Count)
                _jointActionBuf = new int[Agents.Count];

            for (int i = 0; i < Agents.Count; i++)
            {
                var a = Agents[i];
                _jointActionBuf[i] = (a != null && a.LastAction >= 0)
                    ? a.LastAction
                    : ChefSimulation.Action_STAY;
            }
            return Tick(_jointActionBuf);
        }

        // ---------------------------------------------------------------------
        // Reward queue (legacy API kept for ChefAgent / HumanPlayDriver)
        // ---------------------------------------------------------------------

        /// <summary>Record a soup delivery. Score / SoupsServed are owned by
        /// the simulation; this only nudges the per-agent reward queue.</summary>
        public void RegisterSoupDelivery(ChefAgent server)
        {
            AddReward(server, SoupReward);
        }

        public void AddReward(ChefAgent agent, float delta)
        {
            if (agent == null) return;
            if (!_pendingRewards.TryGetValue(agent, out float current)) current = 0f;
            _pendingRewards[agent] = current + delta;
        }

        public float ConsumeReward(ChefAgent agent)
        {
            if (agent == null) return 0f;
            if (!_pendingRewards.TryGetValue(agent, out float r)) return 0f;
            _pendingRewards[agent] = 0f;
            return r;
        }

        // ---------------------------------------------------------------------
        // Adjacency helpers (kept for back-compat with old ChefAgent code paths)
        // ---------------------------------------------------------------------

        public PotController PotAt(int x, int y) => FindPotAt(x, y);

        public bool InBounds(int x, int y)
        {
            if (_simulation == null) return false;
            return x >= 0 && x < _simulation.Layout.Width &&
                   y >= 0 && y < _simulation.Layout.Height;
        }

        private PotController FindPotAt(int x, int y)
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
    }
}
