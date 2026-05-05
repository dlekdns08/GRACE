// StateSerializer.cs
// Phase 6 (Unity ML-Agents scaffolding) for GRACE.
// See DESIGN.md section 4.1.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using Unity.MLAgents.SideChannels;

namespace GRACE.Unity
{
    /// <summary>
    /// ML-Agents side channel that ships a textual rendering of the kitchen
    /// from Unity to the Python wrapper. Format is locked to v1 of
    /// <c>src/envs/state_text.py</c> so cross-env tests can compare strings
    /// byte-for-byte.
    /// </summary>
    public class StateSerializer : SideChannel
    {
        // Must match src/envs/unity_env.py.
        public static readonly Guid SideChannelId =
            new Guid("621f0a70-4f87-11ea-a6bf-784f4387d1f7");

        // Format version. Bumping this invalidates any cached LLM responses
        // keyed off the textual state — keep in lock-step with state_text.py.
        public const string FormatVersion = "v1";

        public StateSerializer()
        {
            ChannelId = SideChannelId;
        }

        /// <summary>
        /// Render <paramref name="k"/> to the v1 textual format. Agents are
        /// sorted alphabetically by <see cref="ChefAgent.AgentName"/>; pots are
        /// rendered in their list order.
        /// </summary>
        public string SerializeKitchen(KitchenEnvironment k)
        {
            if (k == null) return string.Empty;

            // Use invariant culture so commas/dots aren't localised.
            var ic = CultureInfo.InvariantCulture;
            var sb = new StringBuilder(256);

            sb.Append("Step: ").Append(k.Step.ToString(ic))
              .Append('/').Append(k.MaxSteps.ToString(ic)).Append('\n');
            sb.Append("Score: ").Append(k.Score.ToString(ic))
              .Append(" (soups served: ").Append(k.SoupsServed.ToString(ic)).Append(")\n");
            sb.Append('\n');

            // Agents block.
            sb.Append("Agents:\n");
            var sortedAgents = new List<ChefAgent>(k.Agents);
            sortedAgents.Sort((a, b) =>
            {
                string an = a != null ? (a.AgentName ?? string.Empty) : string.Empty;
                string bn = b != null ? (b.AgentName ?? string.Empty) : string.Empty;
                return string.CompareOrdinal(an, bn);
            });

            foreach (var agent in sortedAgents)
            {
                if (agent == null) continue;
                string held = HeldName(agent.HeldItem);
                sb.Append("  - ").Append(agent.AgentName ?? "agent")
                  .Append(" at (").Append(agent.GridX.ToString(ic))
                  .Append(',').Append(agent.GridY.ToString(ic))
                  .Append("), holding ").Append(held).Append('\n');
            }

            sb.Append('\n');
            sb.Append("Pots:\n");
            for (int i = 0; i < k.Pots.Count; i++)
            {
                var p = k.Pots[i];
                sb.Append("  - Pot ").Append(i.ToString(ic)).Append(": ");
                if (p == null || p.IsEmpty)
                {
                    sb.Append("empty");
                }
                else if (p.IsReady)
                {
                    sb.Append("ready to serve");
                }
                else if (p.IsCooking)
                {
                    sb.Append("cooking, ")
                      .Append(p.CookingTime.ToString(ic))
                      .Append("s remaining");
                }
                else
                {
                    sb.Append(p.OnionsIn.ToString(ic))
                      .Append("/3 onions, not started");
                }
                sb.Append('\n');
            }

            return sb.ToString();
        }

        /// <summary>
        /// Convenience: serialize the kitchen and push it over the side
        /// channel. Call this after <see cref="KitchenEnvironment.Tick"/>.
        /// </summary>
        public void SendKitchen(KitchenEnvironment k)
        {
            // TODO(phase6): the user needs to wire this call into their main
            // loop (e.g. inside KitchenSideChannelHook or a dedicated tick
            // driver). Side channels can only be sent while the env is alive,
            // so the hook below is intentionally minimal.
            string payload = SerializeKitchen(k);
            using (var msg = new OutgoingMessage())
            {
                msg.WriteString(payload);
                QueueMessageToSend(msg);
            }
        }

        /// <inheritdoc />
        protected override void OnMessageReceived(IncomingMessage msg)
        {
            // Stub: the Python side does not currently send anything. Drain
            // the message so ML-Agents does not warn about unread bytes.
            if (msg == null) return;
            try { msg.ReadString(); } catch { /* nothing to read */ }
        }

        private static string HeldName(ChefAgent.Item item)
        {
            switch (item)
            {
                case ChefAgent.Item.Onion: return "onion";
                case ChefAgent.Item.Dish: return "dish";
                case ChefAgent.Item.Soup: return "soup";
                case ChefAgent.Item.None:
                default: return "nothing";
            }
        }
    }
}
