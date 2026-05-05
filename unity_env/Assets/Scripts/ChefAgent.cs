// ChefAgent.cs
// Phase 6 (Unity ML-Agents scaffolding) for GRACE.
// See DESIGN.md section 4.1.

using Unity.MLAgents;
using Unity.MLAgents.Actuators;
using Unity.MLAgents.Sensors;
using UnityEngine;

namespace GRACE.Unity
{
    /// <summary>
    /// One Overcooked chef. Inherits from ML-Agents <see cref="Agent"/>; raw
    /// observations feed the RL policy while the parallel side channel pushes
    /// a textual rendering for the LLM planner.
    /// </summary>
    public class ChefAgent : Agent
    {
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

        [Header("State")]
        public int GridX;
        public int GridY;
        public Item HeldItem = Item.None;

        // Action ids: 0 noop, 1 up, 2 down, 3 left, 4 right, 5 pickup/drop, 6 interact
        public const int ActNoop = 0;
        public const int ActUp = 1;
        public const int ActDown = 2;
        public const int ActLeft = 3;
        public const int ActRight = 4;
        public const int ActPickupDrop = 5;
        public const int ActInteract = 6;

        /// <summary>Discrete action-space size. Mirrors Python action space.</summary>
        public const int NumActions = 7;

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
        /// emits given the current kitchen wiring. Useful for HUD / recorder
        /// metadata; ML-Agents itself doesn't need this.
        /// </summary>
        public int GetCurrentObservationDim()
        {
            // self position (3) + held item (1) = 4
            int dim = 4;
            if (kitchen != null)
            {
                // other agents: position (3) + held item (1) per other.
                int others = Mathf.Max(0, kitchen.Agents.Count - 1);
                dim += others * 4;
                // pots: 3 floats each.
                dim += kitchen.Pots.Count * 3;
                // normalised step.
                dim += 1;
            }
            else
            {
                dim += 1; // matches the 0f fallback emitted in CollectObservations.
            }
            return dim;
        }

        public override void OnEpisodeBegin()
        {
            // Only the "first" agent owns the world reset; other agents share it.
            if (kitchen != null && kitchen.Agents.Count > 0 && kitchen.Agents[0] == this)
            {
                kitchen.ResetEpisode();
            }
        }

        public override void CollectObservations(VectorSensor sensor)
        {
            // My own position and held item.
            sensor.AddObservation(transform.localPosition);
            sensor.AddObservation((int)HeldItem);

            // Other agents' positions and held items (stable order from kitchen.Agents).
            if (kitchen != null)
            {
                for (int i = 0; i < kitchen.Agents.Count; i++)
                {
                    var other = kitchen.Agents[i];
                    if (other == null || other == this) continue;
                    sensor.AddObservation(other.transform.localPosition);
                    sensor.AddObservation((int)other.HeldItem);
                }

                // Each pot: (onions, cookingTimeLeft, isReady) as 3 floats.
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

                // Episode step normalised to [0, 1].
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
            ApplyAction(a);
        }

        /// <summary>
        /// Apply a single discrete action to the agent and the kitchen world.
        /// Extracted from <see cref="OnActionReceived"/> so non-ML-Agents
        /// drivers (e.g. <c>HumanPlayDriver</c>) can reuse the same logic
        /// without going through <see cref="ActionBuffers"/>.
        /// </summary>
        /// <remarks>
        /// Side effects mirror <see cref="OnActionReceived"/> exactly:
        /// movement / pickup / interact, step penalty, queued reward
        /// consumption, kitchen tick (only when this is agent 0), and an
        /// <see cref="Agent.EndEpisode"/> call when the kitchen reports done.
        /// </remarks>
        public void ApplyAction(int discreteAction)
        {
            int a = discreteAction;
            LastAction = a;

            int nx = GridX;
            int ny = GridY;
            switch (a)
            {
                case ActUp: ny = GridY + 1; break;
                case ActDown: ny = GridY - 1; break;
                case ActLeft: nx = GridX - 1; break;
                case ActRight: nx = GridX + 1; break;
                case ActPickupDrop: HandlePickupDrop(); break;
                case ActInteract: HandleInteract(); break;
                case ActNoop:
                default: break;
            }

            if (a >= ActUp && a <= ActRight && kitchen != null && kitchen.InBounds(nx, ny))
            {
                if (!IsCellOccupiedByOtherAgent(nx, ny))
                {
                    GridX = nx;
                    GridY = ny;
                    transform.localPosition = new Vector3(nx, transform.localPosition.y, ny);
                }
            }

            // Step penalty plus any reward queued by the kitchen (e.g. soup served).
            AddReward(StepPenalty);
            if (kitchen != null)
            {
                AddReward(kitchen.ConsumeReward(this));
            }

            // Advance the world only on agent 0 to avoid double-stepping.
            if (kitchen != null && kitchen.Agents.Count > 0 && kitchen.Agents[0] == this)
            {
                kitchen.Tick();
            }

            if (kitchen != null && kitchen.IsDone())
            {
                EndEpisode();
            }
        }

        public override void Heuristic(in ActionBuffers actionsOut)
        {
            var discrete = actionsOut.DiscreteActions;
            discrete[0] = ActNoop;

            if (Input.GetKey(KeyCode.W)) discrete[0] = ActUp;
            else if (Input.GetKey(KeyCode.S)) discrete[0] = ActDown;
            else if (Input.GetKey(KeyCode.A)) discrete[0] = ActLeft;
            else if (Input.GetKey(KeyCode.D)) discrete[0] = ActRight;
            else if (Input.GetKey(KeyCode.Space)) discrete[0] = ActPickupDrop;
            else if (Input.GetKey(KeyCode.E)) discrete[0] = ActInteract;
        }

        // ---- helpers --------------------------------------------------------

        private bool IsCellOccupiedByOtherAgent(int x, int y)
        {
            if (kitchen == null) return false;
            for (int i = 0; i < kitchen.Agents.Count; i++)
            {
                var other = kitchen.Agents[i];
                if (other == null || other == this) continue;
                if (other.GridX == x && other.GridY == y) return true;
            }
            return false;
        }

        private void HandlePickupDrop()
        {
            // Toggle: drop whatever we hold; otherwise grab a default onion (the
            // physical counters/dispensers are not modelled in this scaffold).
            if (HeldItem != Item.None)
            {
                HeldItem = Item.None;
            }
            else
            {
                HeldItem = Item.Onion;
            }
        }

        private void HandleInteract()
        {
            if (kitchen == null) return;

            // Look for an adjacent pot (4-neighbourhood).
            PotController pot = kitchen.PotAt(GridX + 1, GridY)
                              ?? kitchen.PotAt(GridX - 1, GridY)
                              ?? kitchen.PotAt(GridX, GridY + 1)
                              ?? kitchen.PotAt(GridX, GridY - 1);
            if (pot == null) return;

            if (HeldItem == Item.Onion)
            {
                if (pot.TryAddOnion()) HeldItem = Item.None;
                return;
            }

            if (HeldItem == Item.Dish && pot.IsReady)
            {
                pot.TryServe(this);
                return;
            }

            if (HeldItem == Item.Soup)
            {
                // Deliver: clears soup and credits the team.
                HeldItem = Item.None;
                kitchen.RegisterSoupDelivery(this);
            }
        }
    }
}
