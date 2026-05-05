// ActionIndexMapTests.cs
// EditMode tests for the GRACE ↔ Carroll action-id remap (Phase G6 parity).

using Grace.Unity.Core;
using NUnit.Framework;

namespace Grace.Unity.Tests.EditMode
{
    [TestFixture]
    public class ActionIndexMapTests
    {
        [Test]
        public void RoundTrip_GraceToCarrollToGrace_IsIdentity()
        {
            for (int g = 0; g < ChefSimulation.NumActions; g++)
            {
                int c = ActionIndexMap.ToCarroll(g);
                int back = ActionIndexMap.ToGrace(c);
                Assert.AreEqual(g, back, $"GRACE id {g} did not round-trip (Carroll {c} → {back})");
            }
        }

        [Test]
        public void RoundTrip_CarrollToGraceToCarroll_IsIdentity()
        {
            for (int c = 0; c < ChefSimulation.NumActions; c++)
            {
                int g = ActionIndexMap.ToGrace(c);
                int back = ActionIndexMap.ToCarroll(g);
                Assert.AreEqual(c, back, $"Carroll id {c} did not round-trip (GRACE {g} → {back})");
            }
        }

        [Test]
        public void GraceStay_MapsToCarrollIndexFour()
        {
            // Carroll: [N, S, E, W, STAY, INTERACT] — STAY is index 4.
            Assert.AreEqual(4, ActionIndexMap.ToCarroll(ChefSimulation.Action_STAY));
        }

        [Test]
        public void GraceInteract_MapsToCarrollIndexFive()
        {
            Assert.AreEqual(5, ActionIndexMap.ToCarroll(ChefSimulation.Action_INTERACT));
        }

        [Test]
        public void Names_LengthMatchesNumActions()
        {
            Assert.AreEqual(ChefSimulation.NumActions, ActionIndexMap.Names.Length);
        }
    }
}
