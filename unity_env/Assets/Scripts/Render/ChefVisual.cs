// ChefVisual.cs
// Phase G2 (Render layer) for GRACE.
// See unity_env/GAME_DESIGN.md sections 2 & 4.
//
// Visual driver for one chef. Reads either:
//   * NetworkChefAgent.CurrentState (online play; replicated by host), or
//   * a local Grace.Unity.Core.ChefSimulationState (offline / solo-vs-AI),
// and forwards changes to MovementInterpolator + body rotation + held-item GO.

using Grace.Unity.Core;
using Grace.Unity.Network;
using UnityEngine;

namespace Grace.Unity.Render
{
    /// <summary>Drives one chef's visual transform, facing, and held item from sim state.</summary>
    public sealed class ChefVisual : MonoBehaviour
    {
        [Header("Source (one of these must be set)")]
        public NetworkChefAgent NetworkAgent;
        public ChefSimulationState OfflineState;

        [Header("Visual children")]
        public MovementInterpolator Interpolator;
        public Transform BodyTransform;
        public GameObject HeldOnion;
        public GameObject HeldDish;
        public GameObject HeldSoup;
        public Animator BodyAnimator;

        private int _lastX = int.MinValue;
        private int _lastY = int.MinValue;
        private byte _lastFacing = 255;
        private byte _lastHeld = 255;

        // Diagnostic logging — drops a snapshot once per second so we can see
        // why the visual isn't following the simulated chef.
        private float _diagTimer;

        private void LateUpdate()
        {
            // Periodic diagnostic dump (1 Hz). Wraps state access in a try block
            // so a "not spawned yet" exception doesn't kill the visual loop.
            _diagTimer += Time.deltaTime;
            if (_diagTimer >= 1f)
            {
                _diagTimer = 0f;
                try
                {
                    bool gotState = TryReadState(out int dx, out int dy, out byte df, out byte dh);
                    int playerIndex = -1;
                    bool kitchenAttached = false;
                    int chefsCount = -1;
                    bool agentSpawned = false;
                    if (NetworkAgent != null)
                    {
                        agentSpawned = NetworkAgent.IsSpawned;
                        if (agentSpawned) playerIndex = NetworkAgent.PlayerIndex.Value;
                        if (NetworkAgent.Kitchen != null)
                        {
                            kitchenAttached = true;
                            if (NetworkAgent.Kitchen.IsSpawned && NetworkAgent.Kitchen.Chefs != null)
                                chefsCount = NetworkAgent.Kitchen.Chefs.Count;
                        }
                    }
                    Debug.Log(
                        $"[ChefVisual] {name} " +
                        $"NetworkAgent={(NetworkAgent != null)} " +
                        $"AgentSpawned={agentSpawned} " +
                        $"Interpolator={(Interpolator != null)} " +
                        $"gotState={gotState} " +
                        (gotState ? $"grid=({dx},{dy}) " : "") +
                        $"transform.pos={transform.position} " +
                        $"PlayerIndex={playerIndex} " +
                        $"KitchenAttached={kitchenAttached} " +
                        $"ChefsCount={chefsCount}");
                }
                catch (System.Exception e)
                {
                    Debug.LogWarning($"[ChefVisual] Diagnostic dump threw: {e.GetType().Name}: {e.Message}");
                }
            }

            if (!TryReadState(out int x, out int y, out byte facing, out byte held))
                return;

            // Position update → trigger lerp + walking animation.
            if (x != _lastX || y != _lastY)
            {
                if (Interpolator != null) Interpolator.SetTarget(x, y);
                _lastX = x;
                _lastY = y;
                if (BodyAnimator != null) BodyAnimator.SetBool("Walking", true);
            }
            else
            {
                if (BodyAnimator != null) BodyAnimator.SetBool("Walking", false);
            }

            // Facing update → body yaw.
            if (facing != _lastFacing)
            {
                _lastFacing = facing;
                if (BodyTransform != null)
                {
                    float yaw;
                    switch (facing)
                    {
                        case 0: yaw = 0f; break;     // North → forward (+z is "up" on screen, y→-z so visual up)
                        case 1: yaw = 180f; break;   // South
                        case 2: yaw = 90f; break;    // East
                        case 3: yaw = 270f; break;   // West
                        default: yaw = 0f; break;
                    }
                    BodyTransform.localRotation = Quaternion.Euler(0f, yaw, 0f);
                }
            }

            // Held-item update → toggle child GameObjects.
            if (held != _lastHeld)
            {
                _lastHeld = held;
                if (HeldOnion != null) HeldOnion.SetActive(held == 1);
                if (HeldDish != null) HeldDish.SetActive(held == 2);
                if (HeldSoup != null) HeldSoup.SetActive(held == 3);
            }
        }

        private bool TryReadState(out int x, out int y, out byte facing, out byte held)
        {
            if (NetworkAgent != null)
            {
                var snap = NetworkAgent.CurrentState;
                if (snap.HasValue)
                {
                    var s = snap.Value;
                    x = s.X;
                    y = s.Y;
                    facing = s.Facing;
                    held = s.Held;
                    return true;
                }
            }
            if (OfflineState != null)
            {
                x = OfflineState.Position.X;
                y = OfflineState.Position.Y;
                facing = (byte)OfflineState.Facing;
                held = (byte)OfflineState.Held;
                return true;
            }
            x = 0; y = 0; facing = 0; held = 0;
            return false;
        }
    }
}
