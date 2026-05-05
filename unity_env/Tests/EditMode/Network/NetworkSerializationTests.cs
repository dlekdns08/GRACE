// NetworkSerializationTests.cs
// Phase G-Network for GRACE.
// See unity_env/GAME_DESIGN.md sections 4 & 5.
//
// EditMode tests for the deterministic, side-effect-free pieces of the
// network sync structs. Full networking is integration-only and lives outside
// this assembly.

using Grace.Unity.Core;
using Grace.Unity.Network;
using NUnit.Framework;

namespace Grace.Unity.Network.Tests
{
    public class NetworkSerializationTests
    {
        [Test]
        public void ChefStateNet_From_Equals_For_Identical_Inputs()
        {
            var s1 = new ChefSimulationState(new GridPos(3, 5), (Facing)1, (HeldItem)2);
            var s2 = new ChefSimulationState(new GridPos(3, 5), (Facing)1, (HeldItem)2);
            var a = ChefStateNet.From(s1);
            var b = ChefStateNet.From(s2);
            Assert.IsTrue(a.Equals(b));
            Assert.AreEqual(a.GetHashCode(), b.GetHashCode());
        }

        [Test]
        public void ChefStateNet_From_NotEquals_For_Different_Position()
        {
            var s1 = new ChefSimulationState(new GridPos(3, 5), (Facing)0, (HeldItem)0);
            var s2 = new ChefSimulationState(new GridPos(4, 5), (Facing)0, (HeldItem)0);
            var a = ChefStateNet.From(s1);
            var b = ChefStateNet.From(s2);
            Assert.IsFalse(a.Equals(b));
        }

        [Test]
        public void ChefStateNet_From_Encodes_Enum_To_Byte()
        {
            var s = new ChefSimulationState(new GridPos(0, 0), (Facing)3, (HeldItem)3);
            var n = ChefStateNet.From(s);
            Assert.AreEqual(0, n.X);
            Assert.AreEqual(0, n.Y);
            Assert.AreEqual((byte)3, n.Facing);
            Assert.AreEqual((byte)3, n.Held);
        }

        [Test]
        public void PotStateNet_From_Equals_For_Identical_Inputs()
        {
            var p = new GridPos(2, 7);
            var s1 = new PotState { OnionsIn = 3, CookingTime = 12, IsReady = false };
            var s2 = new PotState { OnionsIn = 3, CookingTime = 12, IsReady = false };
            var a = PotStateNet.From(p, s1);
            var b = PotStateNet.From(p, s2);
            Assert.IsTrue(a.Equals(b));
            Assert.AreEqual(a.GetHashCode(), b.GetHashCode());
        }

        [Test]
        public void PotStateNet_From_NotEquals_For_Different_Cooking_Time()
        {
            var p = new GridPos(2, 7);
            var a = PotStateNet.From(p, new PotState { OnionsIn = 3, CookingTime = 12, IsReady = false });
            var b = PotStateNet.From(p, new PotState { OnionsIn = 3, CookingTime = 13, IsReady = false });
            Assert.IsFalse(a.Equals(b));
        }

        [Test]
        public void PotStateNet_From_Encodes_Position_And_Ready()
        {
            var p = new GridPos(5, 9);
            var s = new PotState { OnionsIn = 3, CookingTime = 20, IsReady = true };
            var n = PotStateNet.From(p, s);
            Assert.AreEqual(5, n.X);
            Assert.AreEqual(9, n.Y);
            Assert.AreEqual((byte)3, n.OnionsIn);
            Assert.AreEqual((byte)20, n.CookingTime);
            Assert.IsTrue(n.IsReady);
        }
    }
}
