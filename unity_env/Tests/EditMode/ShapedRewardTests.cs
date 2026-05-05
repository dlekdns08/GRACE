// ShapedRewardTests.cs
// EditMode tests for the per-agent shaped reward signal added to ChefSimulation.

using Grace.Unity.Core;
using NUnit.Framework;

namespace Grace.Unity.Tests.EditMode
{
    [TestFixture]
    public class ShapedRewardTests
    {
        private static ChefSimulation MakeSim()
        {
            var layout = LayoutLoader.LoadFromString(
                "XPXOX\n" +
                "X1  X\n" +
                "XXDSX\n",
                "shaped");
            return new ChefSimulation(layout);
        }

        [Test]
        public void OnionInPot_AwardsPlacementShaped()
        {
            var sim = MakeSim();
            sim.Chefs[0].Held = HeldItem.Onion;
            sim.Chefs[0].Facing = Facing.North;
            var shaped = new int[1];
            sim.Tick(new[] { ChefSimulation.Action_INTERACT }, shaped);
            Assert.AreEqual(ChefSimulation.Shaped_PlacementInPot, shaped[0]);
            Assert.AreEqual(0, sim.Score, "placement is shaped only — no sparse reward");
        }

        [Test]
        public void DishPickup_NoShaping_WhenNoPotIsCookingOrReady()
        {
            // Empty pots → dish pickup yields no shaped reward.
            var sim = MakeSim();
            sim.Chefs[0].Position = new GridPos(2, 1);
            sim.Chefs[0].Facing = Facing.South;
            var shaped = new int[1];
            sim.Tick(new[] { ChefSimulation.Action_INTERACT }, shaped);
            Assert.AreEqual(HeldItem.Dish, sim.Chefs[0].Held);
            Assert.AreEqual(0, shaped[0]);
        }

        [Test]
        public void DishPickup_ShapedWhenPotIsCooking()
        {
            var sim = MakeSim();
            // Force a pot into a cooking state.
            var potPos = new GridPos(1, 0);
            sim.Pots[potPos].OnionsIn = 3;
            sim.Pots[potPos].CookingTime = 10;
            // Move chef next to dish dispenser and face it.
            sim.Chefs[0].Position = new GridPos(2, 1);
            sim.Chefs[0].Facing = Facing.South;
            var shaped = new int[1];
            sim.Tick(new[] { ChefSimulation.Action_INTERACT }, shaped);
            Assert.AreEqual(HeldItem.Dish, sim.Chefs[0].Held);
            Assert.AreEqual(ChefSimulation.Shaped_DishPickup, shaped[0]);
        }

        [Test]
        public void SoupPickup_ShapedAndServeIsSparse()
        {
            var sim = MakeSim();
            var potPos = new GridPos(1, 0);
            sim.Pots[potPos].OnionsIn = 3;
            sim.Pots[potPos].IsReady = true;
            sim.Chefs[0].Held = HeldItem.Dish;
            sim.Chefs[0].Facing = Facing.North;

            var shaped = new int[1];
            int sparse = sim.Tick(new[] { ChefSimulation.Action_INTERACT }, shaped);
            Assert.AreEqual(HeldItem.Soup, sim.Chefs[0].Held);
            Assert.AreEqual(ChefSimulation.Shaped_SoupPickup, shaped[0]);
            Assert.AreEqual(0, sparse, "picking up the soup is not the +20 serve event");
        }
    }
}
