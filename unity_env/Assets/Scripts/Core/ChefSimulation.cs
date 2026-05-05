// ChefSimulation.cs
// Phase G1 (Core 3D game logic) for GRACE.
//
// The single source of truth for game state. Pure C# — no UnityEngine deps —
// so it can be consumed identically by:
//   * Render/      (visual interpolation client; Phase G2/G3)
//   * Network/     (NGO host-authoritative sync; Network agent)
//   * ML/          (ML-Agents training; thin wrapper)
//   * EditMode/    (NUnit tests; this phase)
//
// Carroll-faithful semantics. See unity_env/GAME_DESIGN.md row 13:
//   Action enum: 0=STAY, 1=N, 2=S, 3=E, 4=W, 5=INTERACT
// Note: this differs from Carroll's Python INDEX_TO_ACTION ordering ([N,S,E,W,STAY,INTERACT]
// at indices 0..5). The enum values above are GRACE's contract; the Python
// parity layer (G6) handles the index remap at the IPC boundary
// (see <see cref="ActionIndexMap"/> and configs/action_remap.json).

using System;
using System.Collections.Generic;

namespace Grace.Unity.Core
{
    /// <summary>Cardinal facing direction. Mirrors <see cref="ChefSimulation.Action_N"/> etc.</summary>
    public enum Facing
    {
        North = 0,
        South = 1,
        East = 2,
        West = 3,
    }

    /// <summary>
    /// One chef's mutable per-tick state inside <see cref="ChefSimulation"/>.
    /// </summary>
    public sealed class ChefSimulationState
    {
        public GridPos Position;
        public Facing Facing;
        public HeldItem Held;

        public ChefSimulationState(GridPos position, Facing facing, HeldItem held = HeldItem.None)
        {
            Position = position;
            Facing = facing;
            Held = held;
        }
    }

    /// <summary>
    /// Pure-C# Carroll-faithful simulation of a single Overcooked episode.
    /// Owns: layout (read-only), chefs, pots, dropped counter items, score,
    /// step counter. Driven externally one tick at a time via <see cref="Tick"/>.
    /// </summary>
    public sealed class ChefSimulation
    {
        // ---- action ids (GRACE contract; see GAME_DESIGN.md) ----------------

        public const int Action_STAY = 0;
        public const int Action_N = 1;
        public const int Action_S = 2;
        public const int Action_E = 3;
        public const int Action_W = 4;
        public const int Action_INTERACT = 5;

        /// <summary>Discrete action-space size.</summary>
        public const int NumActions = 6;

        /// <summary>Reward delta for delivering a soup (Carroll: +20).</summary>
        public const int RewardServe = 20;

        // ---- shaped reward constants (Carroll's defaults) -------------------

        /// <summary>Shaped reward when a chef places an onion into a pot.</summary>
        public const int Shaped_PlacementInPot = 3;

        /// <summary>
        /// Shaped reward when a chef picks up a dish *while a pot is ready or
        /// cooking* (i.e. a dish that is plausibly useful soon).
        /// </summary>
        public const int Shaped_DishPickup = 3;

        /// <summary>Shaped reward when a chef picks up a cooked soup from a pot.</summary>
        public const int Shaped_SoupPickup = 5;

        // ---- public state ---------------------------------------------------

        public readonly KitchenLayout Layout;

        /// <summary>Index = player_id (0-based). Length matches Layout.ChefStarts.Count.</summary>
        public readonly List<ChefSimulationState> Chefs;

        /// <summary>One <see cref="PotState"/> per Pot tile in the layout, keyed by tile pos.</summary>
        public readonly Dictionary<GridPos, PotState> Pots;

        /// <summary>Items dropped on counter tiles (Counter only — not dispensers).</summary>
        public readonly Dictionary<GridPos, HeldItem> CounterItems;

        public int Step;
        public int Score;
        public int SoupsServed;
        public int MaxSteps;

        /// <summary>
        /// Pot-cooking-start dynamics. <c>true</c> = old_dynamics (auto-start
        /// when the 3rd onion lands). <c>false</c> = new_dynamics (a chef must
        /// INTERACT with a non-empty pot to start cooking).
        /// </summary>
        public bool PotAutoStartOnFull = true;

        // ---- ctor / reset ---------------------------------------------------

        /// <summary>
        /// Build a fresh simulation from <paramref name="layout"/>. Spawns one
        /// chef per <see cref="KitchenLayout.ChefStarts"/> entry, all facing
        /// <see cref="Facing.South"/> with empty hands. Allocates one
        /// <see cref="PotState"/> per Pot tile.
        /// </summary>
        public ChefSimulation(KitchenLayout layout, int maxSteps = 400)
        {
            Layout = layout ?? throw new ArgumentNullException(nameof(layout));
            MaxSteps = maxSteps;

            Chefs = new List<ChefSimulationState>(layout.ChefStarts.Count);
            for (int i = 0; i < layout.ChefStarts.Count; i++)
            {
                Chefs.Add(new ChefSimulationState(layout.ChefStarts[i], Facing.South));
            }

            Pots = new Dictionary<GridPos, PotState>();
            for (int x = 0; x < layout.Width; x++)
            {
                for (int y = 0; y < layout.Height; y++)
                {
                    if (layout.Tiles[x, y] == TileKind.Pot)
                        Pots[new GridPos(x, y)] = new PotState();
                }
            }

            CounterItems = new Dictionary<GridPos, HeldItem>();
            Step = 0;
            Score = 0;
            SoupsServed = 0;
        }

        /// <summary>
        /// Reset the simulation to its initial state without re-allocating the
        /// dictionaries. Useful for ML-Agents OnEpisodeBegin which fires
        /// frequently.
        /// </summary>
        public void ResetEpisode()
        {
            Step = 0;
            Score = 0;
            SoupsServed = 0;

            for (int i = 0; i < Chefs.Count; i++)
            {
                Chefs[i].Position = Layout.ChefStarts[i];
                Chefs[i].Facing = Facing.South;
                Chefs[i].Held = HeldItem.None;
            }

            foreach (var p in Pots.Values) p.Reset();
            CounterItems.Clear();
        }

        public bool IsDone() => Step >= MaxSteps;

        public ChefSimulationState GetChef(int idx) => Chefs[idx];

        // ---- tick -----------------------------------------------------------

        /// <summary>
        /// Apply one joint action and advance world by one tick. Returns the
        /// team-summed sparse reward delta (Carroll: +20 per delivered soup).
        /// </summary>
        public int Tick(int[] jointActions) => Tick(jointActions, null);

        /// <summary>
        /// Variant that also writes per-agent shaped rewards into
        /// <paramref name="shapedOut"/> (must be the same length as
        /// <see cref="Chefs"/>, or null to skip shaping output).
        /// </summary>
        /// <remarks>
        /// Order of operations (Carroll-faithful):
        /// <list type="number">
        ///   <item><description>For each chef in player_id order, compute desired position + facing for movement actions. Facing is updated even when movement is blocked.</description></item>
        ///   <item><description>Resolve collisions: any chef whose desired tile coincides with another chef's desired tile, OR any pair of chefs swapping tiles, all stay put. (Mirrors <c>_handle_collisions</c> in <c>overcooked_mdp.py</c>.)</description></item>
        ///   <item><description>Apply movements.</description></item>
        ///   <item><description>For each chef in player_id order, resolve INTERACT against the tile they're now facing.</description></item>
        ///   <item><description>Tick all pots.</description></item>
        ///   <item><description><c>Step++</c>.</description></item>
        /// </list>
        /// </remarks>
        public int Tick(int[] jointActions, int[] shapedOut)
        {
            if (jointActions == null) throw new ArgumentNullException(nameof(jointActions));
            if (jointActions.Length != Chefs.Count)
                throw new ArgumentException(
                    $"jointActions length {jointActions.Length} != #chefs {Chefs.Count}",
                    nameof(jointActions));
            if (shapedOut != null && shapedOut.Length != Chefs.Count)
                throw new ArgumentException(
                    $"shapedOut length {shapedOut.Length} != #chefs {Chefs.Count}",
                    nameof(shapedOut));
            if (shapedOut != null)
                Array.Clear(shapedOut, 0, shapedOut.Length);

            int reward = 0;
            int n = Chefs.Count;

            // 1) Compute desired (pos, facing) per chef. Facing updates always;
            //    desired position = old position if not a movement action OR if
            //    the target tile is non-walkable.
            var oldPos = new GridPos[n];
            var newPos = new GridPos[n];
            var newFacing = new Facing[n];
            for (int i = 0; i < n; i++)
            {
                var chef = Chefs[i];
                oldPos[i] = chef.Position;
                newFacing[i] = chef.Facing;
                newPos[i] = chef.Position;

                int act = jointActions[i];
                if (IsMovement(act))
                {
                    Facing dir = ActionToFacing(act);
                    newFacing[i] = dir; // facing always updates on a directional action
                    GridPos target = chef.Position + DirDelta(dir);
                    if (Layout.IsWalkable(target))
                        newPos[i] = target;
                }
                // STAY and INTERACT leave position and facing unchanged here.
            }

            // 2) Collision resolution.
            //    * Any two chefs with the same target tile → all chefs targeting
            //      that tile stay put.
            //    * Any pair of chefs swapping tiles (A→B, B→A) → both stay put.
            ResolveCollisions(oldPos, newPos);

            // 3) Apply movement / facing.
            for (int i = 0; i < n; i++)
            {
                Chefs[i].Position = newPos[i];
                Chefs[i].Facing = newFacing[i];
            }

            // 4) Resolve INTERACT in player order.
            for (int i = 0; i < n; i++)
            {
                if (jointActions[i] == Action_INTERACT)
                    reward += ResolveInteract(i, shapedOut);
            }

            // 5) Tick all pots.
            foreach (var pot in Pots.Values) pot.Tick();

            // 6) Advance step.
            Step++;

            return reward;
        }

        // ---- helpers --------------------------------------------------------

        private static bool IsMovement(int action) =>
            action == Action_N || action == Action_S || action == Action_E || action == Action_W;

        private static Facing ActionToFacing(int action)
        {
            switch (action)
            {
                case Action_N: return Facing.North;
                case Action_S: return Facing.South;
                case Action_E: return Facing.East;
                case Action_W: return Facing.West;
                default:
                    throw new ArgumentOutOfRangeException(nameof(action));
            }
        }

        /// <summary>
        /// Direction delta. <b>y=0 is the TOP row of the grid</b>, so North
        /// (visually "up") decreases y, matching Carroll's <c>NORTH=(0,-1)</c>.
        /// </summary>
        public static GridPos DirDelta(Facing f)
        {
            switch (f)
            {
                case Facing.North: return new GridPos(0, -1);
                case Facing.South: return new GridPos(0, 1);
                case Facing.East:  return new GridPos(1, 0);
                case Facing.West:  return new GridPos(-1, 0);
                default: return new GridPos(0, 0);
            }
        }

        /// <summary>
        /// In-place: any chef whose proposed move conflicts is forced back to
        /// its old position. Conflicts:
        ///   - two or more chefs target the same cell;
        ///   - any pair swaps cells (A→B and B→A simultaneously).
        /// </summary>
        private static void ResolveCollisions(GridPos[] oldPos, GridPos[] newPos)
        {
            int n = oldPos.Length;
            bool changed;
            // Simple iterative resolver: if any chef gets reverted, that may
            // free a swap-partner; loop until stable. With <= 4 chefs this is
            // O(n^2) per pass and converges in at most n passes.
            do
            {
                changed = false;
                // Same-target conflict.
                for (int i = 0; i < n; i++)
                {
                    for (int j = i + 1; j < n; j++)
                    {
                        if (newPos[i] == newPos[j])
                        {
                            if (newPos[i] != oldPos[i]) { newPos[i] = oldPos[i]; changed = true; }
                            if (newPos[j] != oldPos[j]) { newPos[j] = oldPos[j]; changed = true; }
                        }
                    }
                }
                // Swap conflict.
                for (int i = 0; i < n; i++)
                {
                    for (int j = i + 1; j < n; j++)
                    {
                        if (newPos[i] == oldPos[j] && newPos[j] == oldPos[i] &&
                            (newPos[i] != oldPos[i] || newPos[j] != oldPos[j]))
                        {
                            if (newPos[i] != oldPos[i]) { newPos[i] = oldPos[i]; changed = true; }
                            if (newPos[j] != oldPos[j]) { newPos[j] = oldPos[j]; changed = true; }
                        }
                    }
                }
            } while (changed);
        }

        /// <summary>
        /// True iff at least one pot is currently cooking or already ready —
        /// used to gate the dish-pickup shaped reward.
        /// </summary>
        private bool AnyPotUseful()
        {
            foreach (var pot in Pots.Values)
            {
                if (pot.IsReady || pot.IsCooking) return true;
            }
            return false;
        }

        /// <summary>
        /// Resolve an INTERACT for chef <paramref name="i"/>. Inspects the tile
        /// directly in front of the chef (position + facing delta). Returns
        /// sparse reward delta (only nonzero on serve). Per-agent shaping is
        /// written to <paramref name="shapedOut"/>[i] when not null.
        /// </summary>
        private int ResolveInteract(int i, int[] shapedOut)
        {
            var chef = Chefs[i];
            GridPos front = chef.Position + DirDelta(chef.Facing);
            if (!Layout.InBounds(front)) return 0;
            TileKind kind = Layout.At(front);

            switch (kind)
            {
                case TileKind.Counter:
                    if (chef.Held == HeldItem.None)
                    {
                        // Pick up if something's there.
                        if (CounterItems.TryGetValue(front, out HeldItem itm))
                        {
                            chef.Held = itm;
                            CounterItems.Remove(front);
                        }
                    }
                    else
                    {
                        // Drop if empty.
                        if (!CounterItems.ContainsKey(front))
                        {
                            CounterItems[front] = chef.Held;
                            chef.Held = HeldItem.None;
                        }
                    }
                    return 0;

                case TileKind.OnionDispenser:
                    if (chef.Held == HeldItem.None) chef.Held = HeldItem.Onion;
                    return 0;

                case TileKind.DishDispenser:
                    if (chef.Held == HeldItem.None)
                    {
                        chef.Held = HeldItem.Dish;
                        if (shapedOut != null && AnyPotUseful())
                            shapedOut[i] += Shaped_DishPickup;
                    }
                    return 0;

                case TileKind.Pot:
                    if (!Pots.TryGetValue(front, out PotState pot)) return 0;
                    if (chef.Held == HeldItem.Onion)
                    {
                        if (pot.TryAddOnion(PotAutoStartOnFull))
                        {
                            chef.Held = HeldItem.None;
                            if (shapedOut != null) shapedOut[i] += Shaped_PlacementInPot;
                        }
                    }
                    else if (chef.Held == HeldItem.Dish && pot.IsReady)
                    {
                        if (pot.TryServeTo(out HeldItem replaced))
                        {
                            chef.Held = replaced;
                            if (shapedOut != null) shapedOut[i] += Shaped_SoupPickup;
                        }
                    }
                    else if (!PotAutoStartOnFull && chef.Held == HeldItem.None)
                    {
                        // Carroll new_dynamics: empty hand + non-empty pot →
                        // start cooking via interact. Auto-start path skips this.
                        pot.TryStartCooking();
                    }
                    return 0;

                case TileKind.ServingCounter:
                    if (chef.Held == HeldItem.Soup)
                    {
                        chef.Held = HeldItem.None;
                        Score += RewardServe;
                        SoupsServed++;
                        return RewardServe;
                    }
                    return 0;

                case TileKind.Floor:
                case TileKind.Wall:
                default:
                    return 0;
            }
        }
    }

}
