// PotStateTests.cs
// Phase G1 EditMode tests for the pot state machine.

using Grace.Unity.Core;
using NUnit.Framework;

namespace Grace.Unity.Tests.EditMode
{
    [TestFixture]
    public class PotStateTests
    {
        [Test]
        public void NewPot_IsEmpty()
        {
            var p = new PotState();
            Assert.AreEqual(0, p.OnionsIn);
            Assert.AreEqual(0, p.CookingTime);
            Assert.IsFalse(p.IsReady);
            Assert.IsFalse(p.IsCooking);
            Assert.IsTrue(p.IsEmpty);
        }

        [Test]
        public void AddingThreeOnions_StartsCooking()
        {
            var p = new PotState();
            Assert.IsTrue(p.TryAddOnion());
            Assert.IsTrue(p.TryAddOnion());
            Assert.AreEqual(2, p.OnionsIn);
            Assert.IsFalse(p.IsCooking);

            Assert.IsTrue(p.TryAddOnion());
            Assert.AreEqual(3, p.OnionsIn);
            Assert.IsTrue(p.IsCooking);
            Assert.AreEqual(PotState.CookingDuration, p.CookingTime);
        }

        [Test]
        public void TryAddOnion_RejectsAtMax()
        {
            var p = new PotState();
            p.TryAddOnion(); p.TryAddOnion(); p.TryAddOnion();
            // Now cooking; further onions rejected.
            Assert.IsFalse(p.TryAddOnion());
            Assert.AreEqual(3, p.OnionsIn);
        }

        [Test]
        public void Tick_TransitionsToReadyAfterCookingDuration()
        {
            var p = new PotState();
            p.TryAddOnion(); p.TryAddOnion(); p.TryAddOnion();
            for (int i = 0; i < PotState.CookingDuration; i++)
            {
                Assert.IsFalse(p.IsReady, $"shouldn't be ready before tick {PotState.CookingDuration}");
                p.Tick();
            }
            Assert.IsTrue(p.IsReady);
            Assert.IsFalse(p.IsCooking);
        }

        [Test]
        public void TryServe_OnReadyPot_ReturnsSoupAndResets()
        {
            var p = new PotState();
            p.TryAddOnion(); p.TryAddOnion(); p.TryAddOnion();
            for (int i = 0; i < PotState.CookingDuration; i++) p.Tick();
            Assert.IsTrue(p.IsReady);

            bool ok = p.TryServeTo(out HeldItem item);
            Assert.IsTrue(ok);
            Assert.AreEqual(HeldItem.Soup, item);
            Assert.IsTrue(p.IsEmpty);
            Assert.AreEqual(0, p.OnionsIn);
            Assert.IsFalse(p.IsReady);
        }

        [Test]
        public void TryServe_OnUnreadyPot_FailsAndYieldsNone()
        {
            var p = new PotState();
            p.TryAddOnion();
            bool ok = p.TryServeTo(out HeldItem item);
            Assert.IsFalse(ok);
            Assert.AreEqual(HeldItem.None, item);
            Assert.AreEqual(1, p.OnionsIn); // pot unchanged
        }

        [Test]
        public void Reset_ClearsEverything()
        {
            var p = new PotState();
            p.TryAddOnion(); p.TryAddOnion(); p.TryAddOnion();
            for (int i = 0; i < 5; i++) p.Tick();
            p.Reset();
            Assert.IsTrue(p.IsEmpty);
            Assert.AreEqual(0, p.OnionsIn);
            Assert.AreEqual(0, p.CookingTime);
            Assert.IsFalse(p.IsReady);
        }
    }
}
