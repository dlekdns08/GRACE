// HUD.cs
// Phase G3 (UI layer) for GRACE.
//
// In-game HUD: timer, score, soups served, per-player held item, pot status.
// Reads NetworkKitchen if assigned (online); otherwise reads a local
// ChefSimulation reference (offline).

using Grace.Unity.Core;
using Grace.Unity.Network;
using TMPro;
using UnityEngine;

namespace Grace.Unity.UI
{
    /// <summary>In-game HUD: shows timer, score, soups served, held items, pot status.</summary>
    public sealed class HUD : MonoBehaviour
    {
        [Header("Source (one of these must be set)")]
        public NetworkKitchen Kitchen;
        public ChefSimulation OfflineSim;

        [Header("Tick rate (for converting steps → seconds)")]
        public float TicksPerSecond = 8f;

        [Header("Text fields")]
        public TMP_Text TimerText;
        public TMP_Text ScoreText;
        public TMP_Text SoupsText;
        public TMP_Text Player1HeldText;
        public TMP_Text Player2HeldText;
        public TMP_Text PotsText;

        private void Update()
        {
            int step, score, soups, maxSteps;
            string p1Held, p2Held, pots;
            if (Kitchen != null)
            {
                step = Kitchen.Step.Value;
                score = Kitchen.Score.Value;
                soups = Kitchen.SoupsServed.Value;
                maxSteps = 400;     // Carroll default; mirrored by NetworkKitchen.LoadAndStart
                p1Held = (Kitchen.Chefs.Count > 0) ? HeldName(Kitchen.Chefs[0].Held) : "—";
                p2Held = (Kitchen.Chefs.Count > 1) ? HeldName(Kitchen.Chefs[1].Held) : "—";
                pots = SummarizeNetPots();
            }
            else if (OfflineSim != null)
            {
                step = OfflineSim.Step;
                score = OfflineSim.Score;
                soups = OfflineSim.SoupsServed;
                maxSteps = OfflineSim.MaxSteps;
                p1Held = (OfflineSim.Chefs.Count > 0) ? OfflineSim.Chefs[0].Held.ToString() : "—";
                p2Held = (OfflineSim.Chefs.Count > 1) ? OfflineSim.Chefs[1].Held.ToString() : "—";
                pots = SummarizeOfflinePots();
            }
            else
            {
                return;
            }

            float remaining = Mathf.Max(0f, (maxSteps - step) / TicksPerSecond);
            if (TimerText != null) TimerText.text = $"{remaining:0.0}s";
            if (ScoreText != null) ScoreText.text = $"Score: {score}";
            if (SoupsText != null) SoupsText.text = $"Soups: {soups}";
            if (Player1HeldText != null) Player1HeldText.text = $"P1: {p1Held}";
            if (Player2HeldText != null) Player2HeldText.text = $"P2: {p2Held}";
            if (PotsText != null) PotsText.text = pots;
        }

        private static string HeldName(byte b)
        {
            switch (b)
            {
                case 1: return "Onion";
                case 2: return "Dish";
                case 3: return "Soup";
                default: return "—";
            }
        }

        private string SummarizeNetPots()
        {
            if (Kitchen == null || Kitchen.Pots == null || Kitchen.Pots.Count == 0) return "—";
            var sb = new System.Text.StringBuilder();
            for (int i = 0; i < Kitchen.Pots.Count; i++)
            {
                var p = Kitchen.Pots[i];
                string state;
                if (p.IsReady) state = "ready";
                else if (p.CookingTime > 0) state = $"cooking {p.CookingTime}";
                else if (p.OnionsIn > 0) state = $"{p.OnionsIn}/3";
                else state = "empty";
                if (i > 0) sb.Append("  ");
                sb.Append($"Pot{i}: {state}");
            }
            return sb.ToString();
        }

        private string SummarizeOfflinePots()
        {
            if (OfflineSim == null || OfflineSim.Pots.Count == 0) return "—";
            var sb = new System.Text.StringBuilder();
            int i = 0;
            foreach (var pot in OfflineSim.Pots.Values)
            {
                string state;
                if (pot.IsReady) state = "ready";
                else if (pot.IsCooking) state = $"cooking {pot.CookingTime}";
                else if (pot.OnionsIn > 0) state = $"{pot.OnionsIn}/3";
                else state = "empty";
                if (i > 0) sb.Append("  ");
                sb.Append($"Pot{i}: {state}");
                i++;
            }
            return sb.ToString();
        }
    }
}
