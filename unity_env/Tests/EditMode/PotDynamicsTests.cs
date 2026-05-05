// PotDynamicsTests.cs
// EditMode tests for the configurable old/new pot dynamics added in A5.

using Grace.Unity.Core;
using NUnit.Framework;

namespace Grace.Unity.Tests.EditMode
{
    [TestFixture]
    public class PotDynamicsTests
    {
        [Test]
        public void NewDynamics_ThirdOnion_DoesNotAutoStart()
        {
            var p = new PotState();
            // explicit autoStart=false (Carroll new_dynamics).
            Assert.IsTrue(p.TryAddOnion(false));
            Assert.IsTrue(p.TryAddOnion(false));
            Assert.IsTrue(p.TryAddOnion(false));
            Assert.AreEqual(3, p.OnionsIn);
            Assert.IsFalse(p.IsCooking, "new_dynamics: 3rd onion should not auto-start cooking");
            Assert.AreEqual(0, p.CookingTime);
        }

        [Test]
        public void NewDynamics_TryStartCooking_StartsWithOneOnion()
        {
            var p = new PotState();
            p.TryAddOnion(false);
            Assert.IsTrue(p.TryStartCooking());
            Assert.IsTrue(p.IsCooking);
            Assert.AreEqual(PotState.CookingDuration, p.CookingTime);
        }

        [Test]
        public void TryStartCooking_RejectsEmptyPot()
        {
            var p = new PotState();
            Assert.IsFalse(p.TryStartCooking());
            Assert.IsFalse(p.IsCooking);
        }

        [Test]
        public void OldDynamics_ThirdOnion_AutoStarts()
        {
            // Default behavior (autoStartOnFull=true).
            var p = new PotState();
            p.TryAddOnion(true);
            p.TryAddOnion(true);
            p.TryAddOnion(true);
            Assert.IsTrue(p.IsCooking);
        }

        [Test]
        public void Sim_NewDynamics_InteractWithFullPot_StartsCooking()
        {
            // Build a tiny layout, place a chef next to a 3-onion pot, set the
            // sim to new_dynamics, and verify INTERACT with empty hand starts
            // cooking on a non-empty pot.
            var layout = LayoutLoader.LoadFromString(
                "XPXOX\n" +
                "X1  X\n" +
                "XXDSX\n",
                "new_dyn");
            var sim = new ChefSimulation(layout) { PotAutoStartOnFull = false };
            var potPos = new GridPos(1, 0);
            sim.Pots[potPos].OnionsIn = 2; // partially filled
            sim.Chefs[0].Facing = Facing.North;
            sim.Chefs[0].Held = HeldItem.None;

            sim.Tick(new[] { ChefSimulation.Action_INTERACT });
            Assert.IsTrue(sim.Pots[potPos].IsCooking,
                "new_dynamics: empty hand + non-empty pot + INTERACT should start cooking");
        }
    }
}
