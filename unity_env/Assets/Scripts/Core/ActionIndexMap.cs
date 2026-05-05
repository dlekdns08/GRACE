// ActionIndexMap.cs
// Phase G6 (Carroll parity layer) for GRACE.
//
// Defines the canonical remap between GRACE's action enum (0=STAY, 1=N, 2=S,
// 3=E, 4=W, 5=INTERACT) and Carroll's overcooked-ai Python ordering
// ([N, S, E, W, STAY, INTERACT] at indices 0..5).
//
// The remap arrays are duplicated in JSON at Resources/Config/action_remap.json
// (also loaded by src/envs/action_remap.py on the Python side). The C# constants
// here are the runtime-fast path; the JSON is the human-editable source of
// truth. A unit test in Tests/EditMode verifies they match.

namespace Grace.Unity.Core
{
    /// <summary>
    /// Static lookup tables for converting between GRACE's action ids and
    /// Carroll's Python ordering. Use whenever crossing the IPC / parity boundary.
    /// </summary>
    public static class ActionIndexMap
    {
        public const int Version = 1;

        /// <summary>Human-readable names indexed by GRACE id.</summary>
        public static readonly string[] Names = { "STAY", "N", "S", "E", "W", "INTERACT" };

        /// <summary>Map a GRACE action id (0..5) to Carroll's index.</summary>
        public static readonly int[] GraceToCarroll = { 4, 0, 1, 2, 3, 5 };

        /// <summary>Map a Carroll action id (0..5) to GRACE's index.</summary>
        public static readonly int[] CarrollToGrace = { 1, 2, 3, 4, 0, 5 };

        /// <summary>Convert a single GRACE id to its Carroll equivalent.</summary>
        public static int ToCarroll(int graceId) => GraceToCarroll[graceId];

        /// <summary>Convert a single Carroll id to its GRACE equivalent.</summary>
        public static int ToGrace(int carrollId) => CarrollToGrace[carrollId];
    }
}
