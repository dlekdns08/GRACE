// HumanPlayDriver.cs
// Phase G1: moved to Grace.Unity.ML; action space updated to Carroll's
// 6-action enum. Logic otherwise unchanged from Phase 9.

using System.Collections.Generic;
using Grace.Unity.Recording;
using UnityEngine;

namespace Grace.Unity.ML
{
    /// <summary>
    /// Fixed-rate driver for human-play mode. Polls each <see cref="PlayerInput"/>
    /// every frame (latching at most one action per tick), then once per tick:
    ///   1. Applies each player's latched action via <see cref="ChefAgent.ApplyAction"/>.
    ///   2. Note: <see cref="ChefAgent.ApplyAction"/> already calls
    ///      <see cref="KitchenEnvironment.Tick"/> when invoked on agent 0,
    ///      so we deliberately do NOT tick again here — we just process all
    ///      agents in order.
    ///   3. Records the (state, action) pair via <see cref="TrajectoryRecorder"/>.
    ///   4. Resets the kitchen if the episode terminated.
    /// </summary>
    public class HumanPlayDriver : MonoBehaviour
    {
        [Header("Mode")]
        [Tooltip("Enable to drive the kitchen from keyboard input. " +
                 "When false, this component is a no-op (ML-Agents Academy " +
                 "drives stepping instead).")]
        public bool humanMode = false;

        [Tooltip("Simulation ticks per second. 8 Hz roughly matches the " +
                 "Carroll Overcooked-AI default and keeps two-player input " +
                 "responsive without skipping key presses.")]
        public float ticksPerSecond = 8f;

        [Header("Refs")]
        public KitchenEnvironment kitchen;
        public List<PlayerInput> players = new List<PlayerInput>();

        [Header("Optional Refs")]
        [Tooltip("If set, each tick is recorded to disk as JSON Lines.")]
        public TrajectoryRecorder recorder;

        [Tooltip("If set, KitchenHUD.Refresh() is called explicitly each tick. " +
                 "Otherwise the HUD updates on LateUpdate as usual.")]
        public KitchenHUD hud;

        // Action latched between ticks for each player. We latch on key-down
        // so a tap that lands between two ticks isn't dropped.
        private readonly List<int> _pendingActions = new List<int>();
        private float _tickAccumulator;
        private bool _started;

        private void OnEnable()
        {
            EnsureSlots();
        }

        private void Start()
        {
            EnsureSlots();
            if (humanMode && kitchen != null && !_started)
            {
                kitchen.ResetEpisode();
                _started = true;
            }
        }

        private void Update()
        {
            if (!humanMode) return;
            if (kitchen == null) return;
            EnsureSlots();

            // Poll input every frame; latch the latest non-noop action so we
            // don't lose key-down events between ticks.
            for (int i = 0; i < players.Count; i++)
            {
                var p = players[i];
                if (p == null) continue;
                int a = p.PollAction();
                if (a != ChefAgent.ActNoop)
                {
                    _pendingActions[i] = a;
                }
            }

            // Fire fixed-rate ticks.
            float interval = 1f / Mathf.Max(0.0001f, ticksPerSecond);
            _tickAccumulator += Time.deltaTime;
            while (_tickAccumulator >= interval)
            {
                _tickAccumulator -= interval;
                StepOnce();
            }
        }

        /// <summary>
        /// Single simulation tick. Public so callers can step deterministically
        /// from a test fixture or a custom UI button.
        /// </summary>
        public void StepOnce()
        {
            if (kitchen == null) return;
            EnsureSlots();

            // Apply actions in player-list order. ChefAgent.ApplyAction will
            // also call kitchen.Tick() exactly once when invoked on agent 0.
            int stepBefore = kitchen.Step;
            for (int i = 0; i < players.Count; i++)
            {
                var p = players[i];
                if (p == null || p.agent == null) continue;
                int action = _pendingActions[i];
                p.agent.ApplyAction(action);
                _pendingActions[i] = ChefAgent.ActNoop;

                if (recorder != null)
                {
                    bool done = kitchen.IsDone();
                    // Per-agent reward isn't directly exposed; we record 0
                    // for the per-step reward and rely on Score / SoupsServed
                    // in state_text for downstream BC labels.
                    recorder.Record(i, action, 0f, done);
                }
            }

            if (hud != null) hud.Refresh();

            // Auto-reset on done so two-player play can run continuously.
            if (kitchen.IsDone())
            {
                kitchen.ResetEpisode();
            }

            // Sanity guard: if no agent advanced the kitchen (e.g. agent 0
            // wasn't in the player list), force a tick so cooking timers
            // still progress. We pass STAY for everyone so the world ticks
            // without anyone moving.
            if (kitchen.Step == stepBefore)
            {
                kitchen.TickFromAgentLastActions();
            }
        }

        private void EnsureSlots()
        {
            while (_pendingActions.Count < players.Count) _pendingActions.Add(ChefAgent.ActNoop);
            while (_pendingActions.Count > players.Count) _pendingActions.RemoveAt(_pendingActions.Count - 1);
        }
    }
}
