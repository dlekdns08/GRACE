// PlayerInput.cs
// Phase G1: moved to Grace.Unity.ML; action space updated to Carroll's
// 6-action enum (STAY=0, N=1, S=2, E=3, W=4, INTERACT=5). Pickup/Drop
// (Phase 6's id 5) is folded into INTERACT.

using UnityEngine;

namespace Grace.Unity.ML
{
    /// <summary>
    /// Polls Unity <see cref="Input"/> for one of two player schemes (WASD or
    /// arrow keys) and returns a discrete action id matching
    /// <see cref="ChefAgent"/>'s action space:
    ///
    /// <list type="bullet">
    ///   <item><description>0 = STAY</description></item>
    ///   <item><description>1 = N (up)</description></item>
    ///   <item><description>2 = S (down)</description></item>
    ///   <item><description>3 = E (right)</description></item>
    ///   <item><description>4 = W (left)</description></item>
    ///   <item><description>5 = INTERACT (formerly pickup/drop + interact)</description></item>
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
                if (Input.GetKeyDown(KeyCode.W)) return ChefAgent.ActN;
                if (Input.GetKeyDown(KeyCode.S)) return ChefAgent.ActS;
                if (Input.GetKeyDown(KeyCode.A)) return ChefAgent.ActW;
                if (Input.GetKeyDown(KeyCode.D)) return ChefAgent.ActE;
                if (Input.GetKeyDown(KeyCode.Space) || Input.GetKeyDown(KeyCode.E))
                    return ChefAgent.ActInteract;
            }
            else
            {
                if (Input.GetKeyDown(KeyCode.UpArrow)) return ChefAgent.ActN;
                if (Input.GetKeyDown(KeyCode.DownArrow)) return ChefAgent.ActS;
                if (Input.GetKeyDown(KeyCode.LeftArrow)) return ChefAgent.ActW;
                if (Input.GetKeyDown(KeyCode.RightArrow)) return ChefAgent.ActE;
                if (Input.GetKeyDown(KeyCode.RightShift) || Input.GetKeyDown(KeyCode.RightControl))
                    return ChefAgent.ActInteract;
            }
            return ChefAgent.ActStay;
        }
    }
}
