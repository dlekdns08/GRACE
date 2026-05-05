// KitchenHUD.cs
// Phase 9 (Unity human-play) for GRACE.
//
// Renders the kitchen state on a Unity Canvas so two human players can see
// step / score / held items / pot status while playing.
//
// ----------------------------------------------------------------------------
// Text widget choice: TextMeshPro
// ----------------------------------------------------------------------------
// We default to TextMeshPro (TMPro.TextMeshProUGUI) because it ships with
// Unity 2022.3 LTS by default and renders crisply at any scale. If a project
// does NOT have TextMeshPro installed (e.g. an aggressively trimmed Unity
// install), swap each `TMPro.TextMeshProUGUI` field for
// `UnityEngine.UI.Text` and replace the `using TMPro;` with
// `using UnityEngine.UI;`. The rest of the script is unchanged.
// ----------------------------------------------------------------------------

using TMPro;
using UnityEngine;

namespace GRACE.Unity
{
    /// <summary>
    /// Drives a small read-only HUD. Inspector-drag each text widget; any null
    /// fields are simply skipped so partial setups still work.
    /// </summary>
    public class KitchenHUD : MonoBehaviour
    {
        [Header("Refs")]
        public KitchenEnvironment kitchen;

        [Header("Text widgets")]
        public TextMeshProUGUI stepText;
        public TextMeshProUGUI scoreText;
        public TextMeshProUGUI soupsServedText;
        public TextMeshProUGUI agent0HeldText;
        public TextMeshProUGUI agent1HeldText;
        public TextMeshProUGUI potStatusText;

        private void LateUpdate()
        {
            Refresh();
        }

        /// <summary>
        /// Pull values out of the kitchen and stamp them into the widgets.
        /// Public so <see cref="HumanPlayDriver"/> can force a refresh
        /// immediately after a tick instead of waiting for Unity's LateUpdate.
        /// </summary>
        public void Refresh()
        {
            if (kitchen == null) return;

            if (stepText != null)
                stepText.text = $"Step: {kitchen.Step}/{kitchen.MaxSteps}";
            if (scoreText != null)
                scoreText.text = $"Score: {kitchen.Score}";
            if (soupsServedText != null)
                soupsServedText.text = $"Soups: {kitchen.SoupsServed}";

            if (agent0HeldText != null)
            {
                agent0HeldText.text = (kitchen.Agents.Count >= 1 && kitchen.Agents[0] != null)
                    ? $"P1 ({kitchen.Agents[0].AgentName}): {kitchen.Agents[0].HeldItemName}"
                    : "P1: -";
            }
            if (agent1HeldText != null)
            {
                agent1HeldText.text = (kitchen.Agents.Count >= 2 && kitchen.Agents[1] != null)
                    ? $"P2 ({kitchen.Agents[1].AgentName}): {kitchen.Agents[1].HeldItemName}"
                    : "P2: -";
            }
            if (potStatusText != null)
            {
                potStatusText.text = (kitchen.Pots.Count >= 1 && kitchen.Pots[0] != null)
                    ? PotSummary(kitchen.Pots[0])
                    : "Pot: -";
            }
        }

        private static string PotSummary(PotController p)
        {
            if (p.IsReady) return "Pot: ready!";
            if (p.IsCooking) return $"Pot: cooking ({p.CookingTime}s)";
            if (p.OnionsIn > 0) return $"Pot: {p.OnionsIn}/{PotController.MaxOnions} onions";
            return "Pot: empty";
        }
    }
}
