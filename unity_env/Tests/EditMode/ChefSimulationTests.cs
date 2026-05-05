// ChefSimulationTests.cs
// Phase G1 EditMode tests for the Carroll-faithful core simulation.
//
// Each test builds a tiny purpose-shaped layout from an ASCII string so the
// expected coordinates are self-evident from reading the test.
//
// Reminder of conventions:
//   - y=0 is the TOP row of the layout source.
//   - Facing.North = (0, -1) (decreasing y).
//   - Action ids: STAY=0, N=1, S=2, E=3, W=4, INTERACT=5.

using Grace.Unity.Core;
using NUnit.Framework;

namespace Grace.Unity.Tests.EditMode
{
    [TestFixture]
    public class ChefSimulationTests
    {
        // ---- helpers --------------------------------------------------------

        /// <summary>Step the sim with a single-chef joint action.</summary>
        private static int Step(ChefSimulation sim, int a0)
        {
            return sim.Tick(new[] { a0 });
        }

        /// <summary>Step the sim with a two-chef joint action.</summary>
        private static int Step(ChefSimulation sim, int a0, int a1)
        {
            return sim.Tick(new[] { a0, a1 });
        }

        // ---- movement -------------------------------------------------------

        [Test]
        public void Movement_North_DecrementsY()
        {
            // 5x5, chef 1 in the centre at (2,2). Open floor everywhere except
            // outer wall.
            var layout = LayoutLoader.LoadFromString(
                "XXXXX\n" +
                "X   X\n" +
                "X 1 X\n" +
                "X   X\n" +
                "XXOSX\n",
                "movement");

            var sim = new ChefSimulation(layout);
            Assert.AreEqual(new GridPos(2, 2), sim.Chefs[0].Position);
            Step(sim, ChefSimulation.Action_N);
            Assert.AreEqual(new GridPos(2, 1), sim.Chefs[0].Position);
            Assert.AreEqual(Facing.North, sim.Chefs[0].Facing);
        }

        [Test]
        public void Movement_AllFourDirections()
        {
            var layout = LayoutLoader.LoadFromString(
                "XXXXX\n" +
                "X   X\n" +
                "X 1 X\n" +
                "X   X\n" +
                "XXOSX\n",
                "all_dirs");
            var sim = new ChefSimulation(layout);

            Step(sim, ChefSimulation.Action_E);
            Assert.AreEqual(new GridPos(3, 2), sim.Chefs[0].Position);
            Step(sim, ChefSimulation.Action_S);
            Assert.AreEqual(new GridPos(3, 3), sim.Chefs[0].Position);
            Step(sim, ChefSimulation.Action_W);
            Assert.AreEqual(new GridPos(2, 3), sim.Chefs[0].Position);
            Step(sim, ChefSimulation.Action_N);
            Assert.AreEqual(new GridPos(2, 2), sim.Chefs[0].Position);
        }

        [Test]
        public void Movement_BlockedByCounter_LeavesPositionButUpdatesFacing()
        {
            // Chef 1 at (1,2) with a Counter directly W (at (0,2) — outer wall).
            var layout = LayoutLoader.LoadFromString(
                "XXXXX\n" +
                "X   X\n" +
                "X1  X\n" +
                "X   X\n" +
                "XXOSX\n",
                "blocked");
            var sim = new ChefSimulation(layout);

            Assert.AreEqual(new GridPos(1, 2), sim.Chefs[0].Position);
            Step(sim, ChefSimulation.Action_W);
            Assert.AreEqual(new GridPos(1, 2), sim.Chefs[0].Position); // unchanged
            Assert.AreEqual(Facing.West, sim.Chefs[0].Facing);         // still rotates
        }

        [Test]
        public void Movement_StayAction_DoesNothing()
        {
            var layout = LayoutLoader.LoadFromString(
                "XXXXX\n" +
                "X1  X\n" +
                "X   X\n" +
                "X   X\n" +
                "XXOSX\n",
                "stay");
            var sim = new ChefSimulation(layout);
            var oldFacing = sim.Chefs[0].Facing;
            Step(sim, ChefSimulation.Action_STAY);
            Assert.AreEqual(new GridPos(1, 1), sim.Chefs[0].Position);
            Assert.AreEqual(oldFacing, sim.Chefs[0].Facing);
        }

        [Test]
        public void Collision_TwoChefsTargetSameTile_NeitherMoves()
        {
            // Two chefs flanking the same target floor cell at (2,1).
            // Layout is 5 cols, 3 rows. Chef 1 at (1,1) (will move E to (2,1)),
            // chef 2 at (3,1) (will move W to (2,1)).
            var layout = LayoutLoader.LoadFromString(
                "XXXXX\n" +
                "X1 2X\n" +
                "XXOSX\n",
                "collide");
            var sim = new ChefSimulation(layout);
            Assert.AreEqual(new GridPos(1, 1), sim.Chefs[0].Position);
            Assert.AreEqual(new GridPos(3, 1), sim.Chefs[1].Position);

            Step(sim, ChefSimulation.Action_E, ChefSimulation.Action_W);

            // Both stayed put.
            Assert.AreEqual(new GridPos(1, 1), sim.Chefs[0].Position);
            Assert.AreEqual(new GridPos(3, 1), sim.Chefs[1].Position);
            // But both updated facing.
            Assert.AreEqual(Facing.East, sim.Chefs[0].Facing);
            Assert.AreEqual(Facing.West, sim.Chefs[1].Facing);
        }

        [Test]
        public void Collision_TwoChefsSwap_NeitherMoves()
        {
            // Adjacent chefs trying to swap (A→B, B→A) — Carroll: both stay.
            var layout = LayoutLoader.LoadFromString(
                "XXXXX\n" +
                "X12 X\n" +
                "XXOSX\n",
                "swap");
            var sim = new ChefSimulation(layout);
            // Chef 1 at (1,1), chef 2 at (2,1).
            Step(sim, ChefSimulation.Action_E, ChefSimulation.Action_W);
            Assert.AreEqual(new GridPos(1, 1), sim.Chefs[0].Position);
            Assert.AreEqual(new GridPos(2, 1), sim.Chefs[1].Position);
        }

        // ---- interactions ---------------------------------------------------

        [Test]
        public void Interact_PickupOnion()
        {
            // Chef 1 at (1,1) facing N (toward an onion dispenser at (1,0)).
            var layout = LayoutLoader.LoadFromString(
                "XOXXX\n" +
                "X1  X\n" +
                "XXDSX\n",
                "pickup_onion");
            var sim = new ChefSimulation(layout);
            // First step: face North.
            Step(sim, ChefSimulation.Action_N); // movement blocked (counter on row 0 col 1 is OnionDispenser, non-walkable)
            Assert.AreEqual(new GridPos(1, 1), sim.Chefs[0].Position);
            Assert.AreEqual(Facing.North, sim.Chefs[0].Facing);
            Assert.AreEqual(HeldItem.None, sim.Chefs[0].Held);

            Step(sim, ChefSimulation.Action_INTERACT);
            Assert.AreEqual(HeldItem.Onion, sim.Chefs[0].Held);
        }

        [Test]
        public void Interact_AddOnionToPot_CountsAndEmptiesHand()
        {
            // Chef 1 at (1,1) facing N (toward Pot at (1,0)).
            var layout = LayoutLoader.LoadFromString(
                "XPXOX\n" +
                "X1  X\n" +
                "XXDSX\n",
                "pot_add");
            var sim = new ChefSimulation(layout);
            // Hand-place an onion in chef's hand.
            sim.Chefs[0].Held = HeldItem.Onion;
            sim.Chefs[0].Facing = Facing.North;

            Step(sim, ChefSimulation.Action_INTERACT);
            Assert.AreEqual(HeldItem.None, sim.Chefs[0].Held);
            var potPos = new GridPos(1, 0);
            Assert.AreEqual(1, sim.Pots[potPos].OnionsIn);
            Assert.IsFalse(sim.Pots[potPos].IsCooking);
        }

        [Test]
        public void Interact_ThirdOnion_StartsCooking()
        {
            var layout = LayoutLoader.LoadFromString(
                "XPXOX\n" +
                "X1  X\n" +
                "XXDSX\n",
                "pot_full");
            var sim = new ChefSimulation(layout);
            var potPos = new GridPos(1, 0);
            sim.Pots[potPos].OnionsIn = 2; // pre-load
            sim.Chefs[0].Held = HeldItem.Onion;
            sim.Chefs[0].Facing = Facing.North;

            Step(sim, ChefSimulation.Action_INTERACT);
            Assert.AreEqual(3, sim.Pots[potPos].OnionsIn);
            Assert.IsTrue(sim.Pots[potPos].IsCooking);
        }

        [Test]
        public void Interact_FacingNonInteractable_DoesNothing()
        {
            var layout = LayoutLoader.LoadFromString(
                "XXXXX\n" +
                "X 1 X\n" +
                "X   X\n" +
                "XXOSX\n",
                "noop_interact");
            var sim = new ChefSimulation(layout);
            // Chef faces east (toward floor).
            sim.Chefs[0].Facing = Facing.East;
            sim.Chefs[0].Held = HeldItem.Onion;

            Step(sim, ChefSimulation.Action_INTERACT);
            Assert.AreEqual(HeldItem.Onion, sim.Chefs[0].Held); // unchanged
        }

        // ---- counter drop / pickup -----------------------------------------

        [Test]
        public void Interact_DropAndPickupOnCounter()
        {
            // Chef 1 at (1,1), Counter (X) directly N at (1,0).
            var layout = LayoutLoader.LoadFromString(
                "XXXXX\n" +
                "X1  X\n" +
                "XXOSX\n",
                "counter");
            var sim = new ChefSimulation(layout);
            sim.Chefs[0].Facing = Facing.North;
            sim.Chefs[0].Held = HeldItem.Onion;

            // Drop onion on counter.
            Step(sim, ChefSimulation.Action_INTERACT);
            Assert.AreEqual(HeldItem.None, sim.Chefs[0].Held);
            Assert.IsTrue(sim.CounterItems.ContainsKey(new GridPos(1, 0)));
            Assert.AreEqual(HeldItem.Onion, sim.CounterItems[new GridPos(1, 0)]);

            // Pick it up again.
            Step(sim, ChefSimulation.Action_INTERACT);
            Assert.AreEqual(HeldItem.Onion, sim.Chefs[0].Held);
            Assert.IsFalse(sim.CounterItems.ContainsKey(new GridPos(1, 0)));
        }

        // ---- end-to-end serve flow ------------------------------------------

        [Test]
        public void FullServeFlow_ScoresTwenty()
        {
            // 5x4 layout custom-shaped so chef 1 can:
            //   - face N to reach Pot (1,0) for onion add
            //   - face W to reach OnionDispenser (0,1)
            //   - face S to reach DishDispenser at (1,2)
            //   - face E along the floor row to reach ServingCounter
            // Layout:
            //   row 0: X P X X X
            //   row 1: O 1 . . X        (chef at (1,1), floor at (2,1) and (3,1))
            //   row 2: X D X . S        (dish at (1,2); serving at (4,2))
            //   row 3: X X X X X
            //
            // Note: due to ASCII grids, "." is filler; we use ' ' for floor.
            // We keep the floor row 1 connected so chef can walk east later.
            var layout = LayoutLoader.LoadFromString(
                "XPXXX\n" +
                "O1  X\n" +
                "XDX S\n" +
                "XXXXX\n",
                "serve_flow");

            var sim = new ChefSimulation(layout);
            var potPos = new GridPos(1, 0);
            var chef = sim.Chefs[0];
            Assert.AreEqual(new GridPos(1, 1), chef.Position);

            // Step 1: face W, pick up onion (interact toward (0,1) OnionDispenser).
            Step(sim, ChefSimulation.Action_W); // movement blocked, faces W
            Assert.AreEqual(Facing.West, chef.Facing);
            Step(sim, ChefSimulation.Action_INTERACT);
            Assert.AreEqual(HeldItem.Onion, chef.Held);

            // Step 2: face N, drop onion in pot.
            Step(sim, ChefSimulation.Action_N); // blocked by Pot tile, faces N
            Assert.AreEqual(Facing.North, chef.Facing);
            Step(sim, ChefSimulation.Action_INTERACT);
            Assert.AreEqual(HeldItem.None, chef.Held);
            Assert.AreEqual(1, sim.Pots[potPos].OnionsIn);

            // Step 3+4: pick up + deposit two more onions.
            Step(sim, ChefSimulation.Action_W);
            Step(sim, ChefSimulation.Action_INTERACT); // pick up
            Step(sim, ChefSimulation.Action_N);
            Step(sim, ChefSimulation.Action_INTERACT); // pot 2/3
            Assert.AreEqual(2, sim.Pots[potPos].OnionsIn);

            Step(sim, ChefSimulation.Action_W);
            Step(sim, ChefSimulation.Action_INTERACT); // pick up
            Step(sim, ChefSimulation.Action_N);
            Step(sim, ChefSimulation.Action_INTERACT); // pot 3/3 -> cooking starts
            Assert.AreEqual(3, sim.Pots[potPos].OnionsIn);
            Assert.IsTrue(sim.Pots[potPos].IsCooking);

            // Step 5: face S, grab a dish from DishDispenser at (1,2).
            //         (We're at (1,1) facing N; switch to S.)
            Step(sim, ChefSimulation.Action_S); // movement blocked by Dish at (1,2) — non-floor
            Assert.AreEqual(Facing.South, chef.Facing);
            Step(sim, ChefSimulation.Action_INTERACT);
            Assert.AreEqual(HeldItem.Dish, chef.Held);

            // Step 6: wait for the pot. We've spent some ticks already; sub-tract
            //         the ticks accumulated since the third onion went in. To be
            //         robust, just STAY until the pot is ready.
            int safety = 0;
            while (!sim.Pots[potPos].IsReady && safety++ < 50)
                Step(sim, ChefSimulation.Action_STAY);
            Assert.IsTrue(sim.Pots[potPos].IsReady, "pot should ready within 50 ticks");

            // Step 7: face N, serve into dish (gives Soup, resets pot).
            Step(sim, ChefSimulation.Action_N);
            Step(sim, ChefSimulation.Action_INTERACT);
            Assert.AreEqual(HeldItem.Soup, chef.Held);
            Assert.IsTrue(sim.Pots[potPos].IsEmpty);

            // Step 8: walk east to (3,1), then face E and INTERACT toward the
            // serving counter at (4,2)... actually layout has serving at (4,2).
            // From (1,1) walk east: (1,1)→(2,1)→(3,1). Floor at (2,1),(3,1)
            // is verified by layout. Then face S to (3,2)? (3,2) is 'X'
            // (Counter), not serving. Let me re-check positions.
            //
            // The serving square is at row=2, col=4 → (4,2). To interact, chef
            // must be on (4,1) facing S, or (3,2) facing E. (4,1) is 'X'
            // counter — not walkable. (3,2) is 'X' — not walkable. So the
            // serving setup needs a free adjacent floor.
            //
            // Re-check layout:
            //   y=0: X P X X X
            //   y=1: O 1 _ _ X      (col 4 is X => not floor)
            //   y=2: X D X _ S      (col 3 is space => floor; col 4 is S)
            //
            // So chef can stand at (3,2) facing E to interact with (4,2). But
            // (3,2) we said is 'X'. Re-read the layout string:
            //   "XPXXX\n"     row 0: X P X X X
            //   "O1  X\n"     row 1: O 1 ' ' ' ' X
            //   "XDX S\n"     row 2: X D X ' ' S
            //   "XXXXX\n"     row 3: X X X X X
            // So (3,2) is ' ' (floor). Perfect. Walking path: (1,1)→(2,1)
            // →(3,1)→(3,2). All floor.

            // Walk E twice, S once.
            Step(sim, ChefSimulation.Action_E);
            Assert.AreEqual(new GridPos(2, 1), chef.Position);
            Step(sim, ChefSimulation.Action_E);
            Assert.AreEqual(new GridPos(3, 1), chef.Position);
            Step(sim, ChefSimulation.Action_S);
            Assert.AreEqual(new GridPos(3, 2), chef.Position);

            // Face E (serving counter at (4,2)).
            Step(sim, ChefSimulation.Action_E); // blocked by ServingCounter, faces E
            Assert.AreEqual(Facing.East, chef.Facing);
            Assert.AreEqual(new GridPos(3, 2), chef.Position);

            // Serve.
            int reward = Step(sim, ChefSimulation.Action_INTERACT);
            Assert.AreEqual(ChefSimulation.RewardServe, reward);
            Assert.AreEqual(20, sim.Score);
            Assert.AreEqual(1, sim.SoupsServed);
            Assert.AreEqual(HeldItem.None, chef.Held);
        }

        // ---- step / done ---------------------------------------------------

        [Test]
        public void Tick_AdvancesStep()
        {
            var layout = LayoutLoader.LoadFromString(
                "XXXXX\n" +
                "X1  X\n" +
                "XXOSX\n",
                "step_count");
            var sim = new ChefSimulation(layout, maxSteps: 3);
            Assert.AreEqual(0, sim.Step);
            Step(sim, ChefSimulation.Action_STAY);
            Assert.AreEqual(1, sim.Step);
            Step(sim, ChefSimulation.Action_STAY);
            Step(sim, ChefSimulation.Action_STAY);
            Assert.AreEqual(3, sim.Step);
            Assert.IsTrue(sim.IsDone());
        }

        [Test]
        public void ResetEpisode_RestoresInitialState()
        {
            var layout = LayoutLoader.LoadFromString(
                "XPXXX\n" +
                "O1  X\n" +
                "XDX S\n" +
                "XXXXX\n",
                "reset");
            var sim = new ChefSimulation(layout);

            sim.Chefs[0].Held = HeldItem.Soup;
            sim.Chefs[0].Position = new GridPos(2, 1);
            sim.Pots[new GridPos(1, 0)].OnionsIn = 2;
            sim.Step = 5;
            sim.Score = 100;
            sim.SoupsServed = 5;

            sim.ResetEpisode();
            Assert.AreEqual(0, sim.Step);
            Assert.AreEqual(0, sim.Score);
            Assert.AreEqual(0, sim.SoupsServed);
            Assert.AreEqual(HeldItem.None, sim.Chefs[0].Held);
            Assert.AreEqual(new GridPos(1, 1), sim.Chefs[0].Position);
            Assert.AreEqual(0, sim.Pots[new GridPos(1, 0)].OnionsIn);
        }
    }
}
