// PlayerInput.cs
// Phase 9 (Unity human-play) for GRACE.
// Maps a keyboard scheme to GRACE's 7-discrete-action space so a
// HumanPlayDriver can poll a player's intent each tick.

using UnityEngine;

namespace GRACE.Unity
{
    /// <summary>
    /// Polls Unity <see cref="Input"/> for one of two player schemes (WASD or
    /// arrow keys) and returns a discrete action id matching
    /// <see cref="ChefAgent"/>'s action space:
    ///
    /// <list type="bullet">
    ///   <item><description>0 = noop</description></item>
    ///   <item><description>1 = up</description></item>
    ///   <item><description>2 = down</description></item>
    ///   <item><description>3 = left</description></item>
    ///   <item><description>4 = right</description></item>
    ///   <item><description>5 = pickup/drop</description></item>
    ///   <item><description>6 = interact</description></item>
    /// </list>
    ///
    /// Uses <c>GetKeyDown</c> so each key press fires exactly once even if a
    /// key is held longer than one tick. The <see cref="HumanPlayDriver"/>
    /// runs at a fixed tick rate (default 8 Hz) which is much slower than
    /// frame rate, so polling-style <c>GetKey</c> would consume the same key
    /// across many ticks.
    /// </summary>
    public class PlayerInput : MonoBehaviour
    {
        public enum PlayerScheme
        {
            WASD = 0,
            Arrows = 1,
        }

        [Tooltip("ChefAgent this input drives. HumanPlayDriver reads this link.")]
        public ChefAgent agent;

        [Tooltip("Keyboard layout for this player.")]
        public PlayerScheme scheme = PlayerScheme.WASD;

        /// <summary>
        /// Returns the discrete action id for the current frame's input.
        /// Should be called from a fixed-rate driver (Update / FixedUpdate /
        /// custom tick) — not multiple times per simulation tick.
        /// </summary>
        public int PollAction()
        {
            if (scheme == PlayerScheme.WASD)
            {
                if (Input.GetKeyDown(KeyCode.W)) return ChefAgent.ActUp;
                if (Input.GetKeyDown(KeyCode.S)) return ChefAgent.ActDown;
                if (Input.GetKeyDown(KeyCode.A)) return ChefAgent.ActLeft;
                if (Input.GetKeyDown(KeyCode.D)) return ChefAgent.ActRight;
                if (Input.GetKeyDown(KeyCode.Space)) return ChefAgent.ActPickupDrop;
                if (Input.GetKeyDown(KeyCode.E)) return ChefAgent.ActInteract;
            }
            else
            {
                if (Input.GetKeyDown(KeyCode.UpArrow)) return ChefAgent.ActUp;
                if (Input.GetKeyDown(KeyCode.DownArrow)) return ChefAgent.ActDown;
                if (Input.GetKeyDown(KeyCode.LeftArrow)) return ChefAgent.ActLeft;
                if (Input.GetKeyDown(KeyCode.RightArrow)) return ChefAgent.ActRight;
                if (Input.GetKeyDown(KeyCode.RightShift)) return ChefAgent.ActPickupDrop;
                if (Input.GetKeyDown(KeyCode.RightControl)) return ChefAgent.ActInteract;
            }
            return ChefAgent.ActNoop;
        }
    }
}
