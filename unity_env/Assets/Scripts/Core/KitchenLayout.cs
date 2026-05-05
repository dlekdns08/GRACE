// KitchenLayout.cs
// Phase G1 (Core 3D game logic) for GRACE.
// See unity_env/GAME_DESIGN.md.
//
// Pure C# (no UnityEngine references). The Core/ namespace is the single
// source of truth for game state; Render, Network, and ML all consume it.

using System;
using System.Collections.Generic;

namespace Grace.Unity.Core
{
    /// <summary>
    /// Kind of tile at a given grid cell. Mirrors the symbols used by Carroll's
    /// Overcooked-AI ASCII layouts (".layout" files) so layouts can be copied
    /// over verbatim.
    /// </summary>
    public enum TileKind
    {
        /// <summary>Walkable empty space (Carroll: ' ').</summary>
        Floor,
        /// <summary>Generic counter — impassable; items can be placed on top (Carroll: 'X').</summary>
        Counter,
        /// <summary>Solid wall — never used by Carroll's standard layouts but kept for future use.</summary>
        Wall,
        /// <summary>Onion source (Carroll: 'O').</summary>
        OnionDispenser,
        /// <summary>Dish source (Carroll: 'D').</summary>
        DishDispenser,
        /// <summary>Cooking pot (Carroll: 'P').</summary>
        Pot,
        /// <summary>Serving counter / delivery point (Carroll: 'S').</summary>
        ServingCounter,
    }

    /// <summary>
    /// Integer 2D position on the kitchen grid. Pure value type, equatable so it
    /// can be a <see cref="Dictionary{TKey,TValue}"/> key.
    /// </summary>
    public struct GridPos : IEquatable<GridPos>
    {
        public int X;
        public int Y;

        public GridPos(int x, int y)
        {
            X = x;
            Y = y;
        }

        public override bool Equals(object o) => o is GridPos g && Equals(g);
        public bool Equals(GridPos g) => X == g.X && Y == g.Y;
        public override int GetHashCode() => (X * 397) ^ Y;
        public static bool operator ==(GridPos a, GridPos b) => a.Equals(b);
        public static bool operator !=(GridPos a, GridPos b) => !a.Equals(b);

        public static GridPos operator +(GridPos a, GridPos b) => new GridPos(a.X + b.X, a.Y + b.Y);
        public static GridPos operator -(GridPos a, GridPos b) => new GridPos(a.X - b.X, a.Y - b.Y);

        public override string ToString() => $"({X},{Y})";
    }

    /// <summary>
    /// An immutable parsed kitchen layout. Coordinates: <c>X</c> is column
    /// (0..Width-1), <c>Y</c> is row (0..Height-1). <b>Y=0 is the TOP row of
    /// the source file</b>, so files read top-down naturally.
    /// </summary>
    public sealed class KitchenLayout
    {
        public readonly int Width;
        public readonly int Height;
        /// <summary>Tile grid, indexed as <c>Tiles[x, y]</c>.</summary>
        public readonly TileKind[,] Tiles;
        /// <summary>Chef start positions, ordered by player index (Carroll '1' = index 0, '2' = index 1, etc.).</summary>
        public readonly List<GridPos> ChefStarts;
        public readonly string Name;

        public KitchenLayout(string name, TileKind[,] tiles, List<GridPos> chefStarts)
        {
            if (tiles == null) throw new ArgumentNullException(nameof(tiles));
            if (chefStarts == null) throw new ArgumentNullException(nameof(chefStarts));

            Name = name ?? "anon";
            Tiles = tiles;
            Width = tiles.GetLength(0);
            Height = tiles.GetLength(1);
            ChefStarts = chefStarts;
        }

        /// <summary>Tile at <paramref name="p"/>. Caller must ensure InBounds.</summary>
        public TileKind At(GridPos p) => Tiles[p.X, p.Y];

        /// <summary>True if <paramref name="p"/> is inside the grid bounds.</summary>
        public bool InBounds(GridPos p) =>
            p.X >= 0 && p.X < Width && p.Y >= 0 && p.Y < Height;

        /// <summary>True if a chef can stand on this tile (only Floor counts).</summary>
        public bool IsWalkable(GridPos p) =>
            InBounds(p) && At(p) == TileKind.Floor;
    }
}
