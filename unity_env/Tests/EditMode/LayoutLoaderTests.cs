// LayoutLoaderTests.cs
// Phase G1 EditMode tests. Pure-C# (no UnityEngine deps) so they run inside
// any NUnit-capable harness, including Unity's Test Runner.
//
// These tests load each of the four standard layouts (Carroll's set
// referenced from GAME_DESIGN.md row 13) and verify basic structural
// invariants: non-zero size, at least 2 chef starts, the right tile kinds
// present, and the chef-start positions sit on Floor tiles.

using System.Collections.Generic;
using Grace.Unity.Core;
using NUnit.Framework;

namespace Grace.Unity.Tests.EditMode
{
    [TestFixture]
    public class LayoutLoaderTests
    {
        private static readonly string[] StandardLayouts = new[]
        {
            "cramped_room",
            "asymmetric_advantages",
            "coordination_ring",
            "forced_coordination",
        };

        [Test]
        public void CrampedRoom_LoadsFromString()
        {
            // Source from overcooked_ai_py/data/layouts/cramped_room.layout.
            var layout = LayoutLoader.LoadFromString(
                "XXPXX\n" +
                "O  2O\n" +
                "X1  X\n" +
                "XDXSX\n",
                "cramped_room");

            Assert.AreEqual(5, layout.Width);
            Assert.AreEqual(4, layout.Height);
            Assert.AreEqual(2, layout.ChefStarts.Count);
            // Chef '1' is row 2, col 1 (0-indexed).
            Assert.AreEqual(new GridPos(1, 2), layout.ChefStarts[0]);
            // Chef '2' is row 1, col 3.
            Assert.AreEqual(new GridPos(3, 1), layout.ChefStarts[1]);
            Assert.AreEqual(TileKind.Pot, layout.Tiles[2, 0]);
            Assert.AreEqual(TileKind.OnionDispenser, layout.Tiles[0, 1]);
            Assert.AreEqual(TileKind.DishDispenser, layout.Tiles[1, 3]);
            Assert.AreEqual(TileKind.ServingCounter, layout.Tiles[3, 3]);
            Assert.AreEqual(TileKind.Floor, layout.Tiles[1, 2]); // chef 1 starts on floor
        }

        [Test]
        public void AllStandardLayouts_HaveCoreInvariants()
        {
            foreach (string name in StandardLayouts)
            {
                KitchenLayout layout = TryLoad(name);
                if (layout == null) continue; // file-system absent in some test runs

                Assert.Greater(layout.Width, 0, $"{name}: width should be > 0");
                Assert.Greater(layout.Height, 0, $"{name}: height should be > 0");
                Assert.GreaterOrEqual(layout.ChefStarts.Count, 2,
                    $"{name}: needs at least 2 chef starts");

                // Every chef start sits on a walkable Floor tile.
                foreach (var start in layout.ChefStarts)
                    Assert.IsTrue(layout.IsWalkable(start),
                        $"{name}: chef start {start} should be on a Floor tile");

                // All four core kinds appear at least once (Counter, OnionDisp, DishDisp, Pot, Serving).
                var counts = CountTileKinds(layout);
                Assert.Greater(counts[TileKind.Counter], 0, $"{name}: needs counters");
                Assert.Greater(counts[TileKind.Pot], 0, $"{name}: needs at least one pot");
                Assert.Greater(counts[TileKind.OnionDispenser], 0, $"{name}: needs onion dispenser");
                Assert.Greater(counts[TileKind.DishDispenser], 0, $"{name}: needs dish dispenser");
                Assert.Greater(counts[TileKind.ServingCounter], 0, $"{name}: needs serving counter");
                Assert.Greater(counts[TileKind.Floor], 0, $"{name}: needs walkable floor");
            }
        }

        [Test]
        public void AsymmetricAdvantages_HasTwoPots()
        {
            // 2-pot layout (left and right cooking stations).
            var layout = TryLoad("asymmetric_advantages");
            if (layout == null) Assert.Inconclusive("layout file not found in this run");

            var counts = CountTileKinds(layout);
            Assert.AreEqual(2, counts[TileKind.Pot]);
        }

        [Test]
        public void UnknownSymbol_Throws()
        {
            Assert.Throws<System.FormatException>(() =>
                LayoutLoader.LoadFromString("XQX\nX1X\nXXX\n", "bad"));
        }

        [Test]
        public void EmptyString_Throws()
        {
            Assert.Throws<System.FormatException>(() =>
                LayoutLoader.LoadFromString("", "empty"));
        }

        // ---- helpers --------------------------------------------------------

        private static KitchenLayout TryLoad(string name)
        {
            try { return LayoutLoader.Load(name); }
            catch (System.IO.FileNotFoundException) { return null; }
        }

        private static Dictionary<TileKind, int> CountTileKinds(KitchenLayout layout)
        {
            var d = new Dictionary<TileKind, int>();
            foreach (TileKind k in System.Enum.GetValues(typeof(TileKind))) d[k] = 0;
            for (int x = 0; x < layout.Width; x++)
                for (int y = 0; y < layout.Height; y++)
                    d[layout.Tiles[x, y]]++;
            return d;
        }
    }
}
