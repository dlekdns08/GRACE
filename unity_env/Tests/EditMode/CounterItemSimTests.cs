// CounterItemSimTests.cs
// EditMode tests verifying that ChefSimulation's CounterItems map evolves
// correctly under drop / pickup. NetworkKitchen replicates this map via
// CounterItemNet (A1); these tests cover the source of truth.

using System.Collections.Generic;
using Grace.Unity.Core;
using NUnit.Framework;

namespace Grace.Unity.Tests.EditMode
{
    [TestFixture]
    public class CounterItemSimTests
    {
        private static ChefSimulation MakeSim()
        {
            var layout = LayoutLoader.LoadFromString(
                "XXXXX\n" +
                "X1  X\n" +
                "XXOSX\n",
                "counter_sim");
            return new ChefSimulation(layout);
        }

        [Test]
        public void Drop_CreatesCounterItemEntry()
        {
            var sim = MakeSim();
            sim.Chefs[0].Held = HeldItem.Onion;
            sim.Chefs[0].Facing = Facing.North;
            sim.Tick(new[] { ChefSimulation.Action_INTERACT });
            Assert.AreEqual(1, sim.CounterItems.Count);
            Assert.AreEqual(HeldItem.Onion, sim.CounterItems[new GridPos(1, 0)]);
        }

        [Test]
        public void Pickup_RemovesCounterItemEntry()
        {
            var sim = MakeSim();
            sim.Chefs[0].Held = HeldItem.Onion;
            sim.Chefs[0].Facing = Facing.North;
            sim.Tick(new[] { ChefSimulation.Action_INTERACT });   // drop
            sim.Tick(new[] { ChefSimulation.Action_INTERACT });   // pick up
            Assert.AreEqual(0, sim.CounterItems.Count);
            Assert.AreEqual(HeldItem.Onion, sim.Chefs[0].Held);
        }

        [Test]
        public void DropOntoOccupiedCounter_DoesNotOverwrite()
        {
            var sim = MakeSim();
            // Pre-place an onion at the counter (1,0).
            sim.CounterItems[new GridPos(1, 0)] = HeldItem.Onion;
            sim.Chefs[0].Held = HeldItem.Dish;
            sim.Chefs[0].Facing = Facing.North;
            sim.Tick(new[] { ChefSimulation.Action_INTERACT });
            Assert.AreEqual(HeldItem.Onion, sim.CounterItems[new GridPos(1, 0)],
                "counter occupied — drop should be a no-op");
            Assert.AreEqual(HeldItem.Dish, sim.Chefs[0].Held,
                "chef should still be holding the original item");
        }

        [Test]
        public void StablePotKeyOrder_IsRowMajor()
        {
            // Two pots at known positions; the ordering used by NetworkKitchen
            // (sort by Y then X) should be deterministic.
            var layout = LayoutLoader.LoadFromString(
                "XPXPX\n" +
                "X1  X\n" +
                "XPXPX\n" +
                "XXOSX\n",
                "two_pots");
            var sim = new ChefSimulation(layout);
            var keys = new List<GridPos>(sim.Pots.Keys);
            keys.Sort((a, b) =>
            {
                int dy = a.Y.CompareTo(b.Y);
                return dy != 0 ? dy : a.X.CompareTo(b.X);
            });
            Assert.AreEqual(new GridPos(1, 0), keys[0]);
            Assert.AreEqual(new GridPos(3, 0), keys[1]);
            Assert.AreEqual(new GridPos(1, 2), keys[2]);
            Assert.AreEqual(new GridPos(3, 2), keys[3]);
        }
    }
}
