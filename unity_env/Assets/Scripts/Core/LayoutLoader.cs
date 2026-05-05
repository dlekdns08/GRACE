// LayoutLoader.cs
// Phase G1 (Core 3D game logic) for GRACE.
// Parses Carroll's Overcooked-AI ASCII layout grids into a KitchenLayout.
//
// Source format (Carroll Overcooked-AI):
//   ' ' = floor
//   'X' = counter
//   'O' = onion dispenser
//   'D' = dish dispenser
//   'P' = pot
//   'S' = serving counter
//   '1', '2', ... = chef start positions (also walkable floor tiles)
//
// Convention: y=0 is the TOP row of the file. We read line-by-line as written.
//
// This file is pure C# — no UnityEngine references — so the Core asmdef can
// run inside EditMode/PlayMode tests and in deterministic unit tests.

using System;
using System.Collections.Generic;
using System.IO;

namespace Grace.Unity.Core
{
    /// <summary>
    /// Static helpers for loading <see cref="KitchenLayout"/>s from Carroll's
    /// ASCII layout format.
    /// </summary>
    public static class LayoutLoader
    {
        /// <summary>
        /// Load a layout by name. The lookup order is:
        /// <list type="number">
        ///   <item><description>Direct file path (if <paramref name="name"/> ends in <c>.txt</c> or <c>.layout</c> and exists on disk).</description></item>
        ///   <item><description><c>Assets/Resources/Layouts/{name}.txt</c> relative to the current working directory.</description></item>
        ///   <item><description><c>{name}.txt</c> in the current directory.</description></item>
        /// </list>
        /// At runtime inside Unity, callers should usually use
        /// <c>UnityEngine.Resources.Load&lt;TextAsset&gt;("Layouts/" + name)</c> and
        /// then pass <c>.text</c> into <see cref="LoadFromString"/>; this static
        /// loader exists primarily for EditMode tests and head-less tooling.
        /// </summary>
        public static KitchenLayout Load(string name)
        {
            if (string.IsNullOrEmpty(name))
                throw new ArgumentException("name must be non-empty", nameof(name));

            string source = ReadLayoutSource(name);
            return LoadFromString(source, BaseName(name));
        }

        /// <summary>
        /// Parse a layout from an in-memory string. Trailing blank lines and
        /// trailing whitespace on each row are trimmed; the grid is right-padded
        /// with counters (<c>X</c>) so all rows reach <c>Width</c>.
        /// </summary>
        public static KitchenLayout LoadFromString(string source, string name = "anon")
        {
            if (source == null) throw new ArgumentNullException(nameof(source));

            // Split on \n, then strip trailing \r so files written on Windows still work.
            // We do NOT TrimStart the line: a leading space is a Floor tile, not
            // formatting whitespace. Authors must keep .txt files flush-left.
            string[] rawLines = source.Split('\n');
            var rows = new List<string>(rawLines.Length);
            for (int i = 0; i < rawLines.Length; i++)
            {
                string line = rawLines[i];
                if (line.Length > 0 && line[line.Length - 1] == '\r')
                    line = line.Substring(0, line.Length - 1);
                rows.Add(line);
            }

            // Drop empty trailing rows (file ends with a newline → empty last line).
            while (rows.Count > 0 && rows[rows.Count - 1].Length == 0)
                rows.RemoveAt(rows.Count - 1);
            // Drop empty leading rows.
            while (rows.Count > 0 && rows[0].Length == 0)
                rows.RemoveAt(0);

            if (rows.Count == 0)
                throw new FormatException($"Layout '{name}' is empty.");

            int height = rows.Count;
            int width = 0;
            for (int y = 0; y < height; y++)
                if (rows[y].Length > width) width = rows[y].Length;

            if (width == 0)
                throw new FormatException($"Layout '{name}' has zero width.");

            var tiles = new TileKind[width, height];
            var chefStartsByIndex = new SortedDictionary<int, GridPos>();

            for (int y = 0; y < height; y++)
            {
                string row = rows[y];
                for (int x = 0; x < width; x++)
                {
                    char c = x < row.Length ? row[x] : 'X'; // pad short rows with counter
                    tiles[x, y] = ParseSymbol(c, x, y, name, out int chefId);
                    if (chefId > 0)
                    {
                        if (chefStartsByIndex.ContainsKey(chefId))
                            throw new FormatException(
                                $"Layout '{name}' declares chef '{chefId}' more than once.");
                        chefStartsByIndex[chefId] = new GridPos(x, y);
                    }
                }
            }

            // Materialise the chef-start list ordered by Carroll player id.
            var chefStarts = new List<GridPos>(chefStartsByIndex.Count);
            foreach (var kv in chefStartsByIndex) chefStarts.Add(kv.Value);

            if (chefStarts.Count == 0)
                throw new FormatException(
                    $"Layout '{name}' must declare at least one chef start ('1').");

            return new KitchenLayout(name, tiles, chefStarts);
        }

        /// <summary>
        /// Parse a single ASCII cell. Returns its <see cref="TileKind"/> and, if
        /// the cell is a chef start digit, the 1-based chef id (otherwise 0).
        /// Chef start cells are <see cref="TileKind.Floor"/>.
        /// </summary>
        private static TileKind ParseSymbol(char c, int x, int y, string name, out int chefId)
        {
            chefId = 0;
            switch (c)
            {
                case ' ':
                    return TileKind.Floor;
                case 'X':
                    return TileKind.Counter;
                case 'O':
                    return TileKind.OnionDispenser;
                case 'D':
                    return TileKind.DishDispenser;
                case 'P':
                    return TileKind.Pot;
                case 'S':
                    return TileKind.ServingCounter;
                default:
                    if (c >= '1' && c <= '9')
                    {
                        chefId = c - '0';
                        return TileKind.Floor;
                    }
                    throw new FormatException(
                        $"Unknown layout symbol '{c}' at ({x},{y}) in layout '{name}'.");
            }
        }

        // ---- file lookup helpers --------------------------------------------

        private static string ReadLayoutSource(string name)
        {
            // If caller passed a path that already exists, use it.
            if (File.Exists(name))
                return File.ReadAllText(name);

            string baseName = BaseName(name);

            string p1 = Path.Combine("Assets", "Resources", "Layouts", baseName + ".txt");
            if (File.Exists(p1)) return File.ReadAllText(p1);

            string p2 = Path.Combine("unity_env", "Assets", "Resources", "Layouts", baseName + ".txt");
            if (File.Exists(p2)) return File.ReadAllText(p2);

            string p3 = baseName + ".txt";
            if (File.Exists(p3)) return File.ReadAllText(p3);

            throw new FileNotFoundException(
                $"Could not find layout '{name}'. Looked at '{p1}', '{p2}', '{p3}'.");
        }

        private static string BaseName(string name)
        {
            string n = name;
            if (n.EndsWith(".txt", StringComparison.OrdinalIgnoreCase))
                n = n.Substring(0, n.Length - 4);
            else if (n.EndsWith(".layout", StringComparison.OrdinalIgnoreCase))
                n = n.Substring(0, n.Length - 7);
            return Path.GetFileName(n);
        }
    }
}
