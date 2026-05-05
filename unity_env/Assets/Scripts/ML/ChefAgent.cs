// ChefAgent.cs
// Phase G1: refactored to a thin ML-Agents Agent that delegates all game
// logic to Grace.Unity.Core.ChefSimulation. Action space collapses from
// 7 (Phase 6) to 6 (Carroll: STAY, N, S, E, W, INTERACT).
//
// Inspector note: the BehaviorParameters component on each ChefAgent
// GameObject MUST have its discrete action branch resized from 7 to 6.

using Grace.Unity.Core;
using Unity.MLAgents;
using Unity.MLAgents.Actuators;
using Unity.MLAgents.Sensors;
using UnityEngine;

namespace Grace.Unity.ML
{
    /// <summary>
    /// One Overcooked chef. Owns no game logic; reads/writes its state through
    /// <see cref="KitchenEnvironment"/> which itself delegates to
    /// <see cref="ChefSimulation"/>.
    /// </summary>
    public class ChefAgent : Agent
    {
        /// <summary>Mirrors <see cref="HeldItem"/>; kept as a nested enum for
        /// inspector display and back-compat with prior Phase 6 code.</summary>
        public enum Item
        {
            None = 0,
            Onion = 1,
            Dish = 2,
            Soup = 3,
        }

        [Header("Identity")]
        public string AgentName = "agent_0";

        [Header("Refs")]
        public KitchenEnvironment kitchen;

        [Header("State (read-only, mirrored from ChefSimulation)")]
        public int GridX;
        public int GridY;
        public Item HeldItem = Item.None;

        // ---- 6-action space (Carroll-faithful) ------------------------------
        public const int ActStay = ChefSimulation.Action_STAY;
        public const int ActN = ChefSimulation.Action_N;
        public const int ActS = ChefSimulation.Action_S;
        public const int ActE = ChefSimulation.Action_E;
        public const int ActW = ChefSimulation.Action_W;
        public const int ActInteract = ChefSimulation.Action_INTERACT;

        /// <summary>Discrete action-space size. Mirrors Python action space.</summary>
        public const int NumActions = ChefSimulation.NumActions;

        // Back-compat aliases used by older code paths (HumanPlayDriver, etc.).
        // Phase 6's separate Pickup/Drop and Up/Down/Left/Right names are
        // remapped onto the 6-action enum: Pickup/Drop becomes INTERACT, and
        // the cardinal aliases just re-export Action_N..Action_W.
        public const int ActNoop = ActStay;
        public const int ActUp = ActN;
        public const int ActDown = ActS;
        public const int ActLeft = ActW;
        public const int ActRight = ActE;
        public const int ActPickupDrop = ActInteract;

        private const float StepPenalty = -0.01f;

        /// <summary>The most recently applied discrete action id (or -1 if none).</summary>
        public int LastAction { get; private set; } = -1;

        /// <summary>Human-readable name of the currently held item.</summary>
        public string HeldItemName
        {
            get
            {
                switch (HeldItem)
                {
                    case Item.Onion: return "onion";
                    case Item.Dish: return "dish";
                    case Item.Soup: return "soup";
                    case Item.None:
                    default: return "nothing";
                }
            }
        }

        /// <summary>
        /// Number of float observations <see cref="CollectObservations"/>
        /// emits given the current kitchen wiring.
        /// </summary>
        public int GetCurrentObservationDim()
        {
            // self position (3) + held item (1) = 4
            int dim = 4;
            if (kitchen != null)
            {
                int others = Mathf.Max(0, kitchen.Agents.Count - 1);
                dim += others * 4;
                int potCount = kitchen.Simulation != null
                    ? kitchen.Simulation.Pots.Count
                    : kitchen.Pots.Count;
                dim += potCount * 3;
                dim += 1; // normalised step
            }
            else
            {
                dim += 1;
            }
            return dim;
        }

        public override void OnEpisodeBegin()
        {
            if (kitchen != null && kitchen.Agents.Count > 0 && kitchen.Agents[0] == this)
            {
                kitchen.ResetEpisode();
            }
        }

        public override void CollectObservations(VectorSensor sensor)
        {
            sensor.AddObservation(transform.localPosition);
            sensor.AddObservation((int)HeldItem);

            if (kitchen != null)
            {
                for (int i = 0; i < kitchen.Agents.Count; i++)
                {
                    var other = kitchen.Agents[i];
                    if (other == null || other == this) continue;
                    sensor.AddObservation(other.transform.localPosition);
                    sensor.AddObservation((int)other.HeldItem);
                }

                // Pots: prefer authoritative simulation state, fall back to MB pots.
                if (kitchen.Simulation != null)
                {
                    foreach (var kv in kitchen.Simulation.Pots)
                    {
                        sensor.AddObservation((float)kv.Value.OnionsIn);
                        sensor.AddObservation((float)kv.Value.CookingTime);
                        sensor.AddObservation(kv.Value.IsReady ? 1f : 0f);
                    }
                }
                else
                {
                    for (int i = 0; i < kitchen.Pots.Count; i++)
                    {
                        var p = kitchen.Pots[i];
                        if (p == null)
                        {
                            sensor.AddObservation(0f);
                            sensor.AddObservation(0f);
                            sensor.AddObservation(0f);
                            continue;
                        }
                        sensor.AddObservation((float)p.OnionsIn);
                        sensor.AddObservation((float)p.CookingTime);
                        sensor.AddObservation(p.IsReady ? 1f : 0f);
                    }
                }

                float maxSteps = Mathf.Max(1, kitchen.MaxSteps);
                sensor.AddObservation(Mathf.Clamp01(kitchen.Step / maxSteps));
            }
            else
            {
                sensor.AddObservation(0f);
            }
        }

        public override void OnActionReceived(ActionBuffers actions)
        {
            int a = actions.DiscreteActions[0];
            // Validate range: if the inspector wasn't bumped to size 6 the
            // policy might still emit 6; clamp to STAY so we never crash.
            if (a < 0 || a >= NumActions) a = ActStay;
            ApplyAction(a);
        }

        /// <summary>
        /// Stage <paramref name="discreteAction"/> as this agent's next move.
        /// The actual world tick fires once per step on agent[0].
        /// </summary>
        public void ApplyAction(int discreteAction)
        {
            int a = discreteAction;
            if (a < 0 || a >= NumActions) a = ActStay;
            LastAction = a;

            // Step penalty (per agent, every tick).
            AddReward(StepPenalty);

            // Only agent[0] drives the world: it gathers each agent's LastAction
            // into a joint-action array and ticks the simulation once. After
            // the tick, each agent's reward queue holds its share of any
            // delivered soup reward.
            if (kitchen != null && kitchen.Agents.Count > 0 && kitchen.Agents[0] == this)
            {
                kitchen.TickFromAgentLastActions();
            }

            // Pull queued reward (e.g. shared soup-delivery share) into ML-Agents.
            if (kitchen != null)
            {
                AddReward(kitchen.ConsumeReward(this));
            }

            if (kitchen != null && kitchen.IsDone())
            {
                EndEpisode();
            }
        }

        public override void Heuristic(in ActionBuffers actionsOut)
        {
            var discrete = actionsOut.DiscreteActions;
            discrete[0] = ActStay;

            if (Input.GetKey(KeyCode.W)) discrete[0] = ActN;
            else if (Input.GetKey(KeyCode.S)) discrete[0] = ActS;
            else if (Input.GetKey(KeyCode.A)) discrete[0] = ActW;
            else if (Input.GetKey(KeyCode.D)) discrete[0] = ActE;
            else if (Input.GetKey(KeyCode.E) || Input.GetKey(KeyCode.Space)) discrete[0] = ActInteract;
        }
    }
}
