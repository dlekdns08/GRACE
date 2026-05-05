// PlayerInputController.cs
// Phase G2 (Input layer) for GRACE.
// See unity_env/GAME_DESIGN.md row 9 (Unity new Input System).
//
// Polls the new Input System (ChefControls.inputactions) and latches the most
// recent meaningful 6-action intent (0=STAY, 1=N, 2=S, 3=E, 4=W, 5=INTERACT)
// for the next sim tick. The simulation driver pulls the latched intent via
// FlushIntent() at the 8 Hz tick boundary and submits it to the network agent
// (online) or local sim (offline).

using Grace.Unity.Core;
using Grace.Unity.Network;
using UnityEngine;
using UnityEngine.InputSystem;

namespace Grace.Unity.Input
{
    /// <summary>Per-player input poller; latches a 6-action intent for the next 8 Hz tick.</summary>
    public sealed class PlayerInputController : MonoBehaviour
    {
        [Header("Player slot")]
        [Tooltip("0 = P1 (WASD/Space), 1 = P2 (Arrows/RShift). Used for action map selection in local-coop.")]
        public int LocalPlayerIndex = 0;

        [Header("Targets (one of these may be set)")]
        public NetworkChefAgent NetworkAgent;
        public ChefSimulation OfflineSim;

        [Header("Input asset")]
        [Tooltip("Drag ChefControls.inputactions here. If null, falls back to legacy Input.")]
        public InputActionAsset Controls;

        // Resolved actions (Input System path).
        private InputAction _moveAction;
        private InputAction _interactAction;

        // Pending intent for the next sim tick. Default STAY (0).
        private int _pending = ChefSimulation.Action_STAY;

        private void OnEnable()
        {
            if (Controls != null)
            {
                string mapName = LocalPlayerIndex == 0 ? "P1" : "P2";
                var map = Controls.FindActionMap(mapName, throwIfNotFound: false);
                if (map != null)
                {
                    _moveAction = map.FindAction("Move", throwIfNotFound: false);
                    _interactAction = map.FindAction("Interact", throwIfNotFound: false);
                    map.Enable();
                }
            }
        }

        private void OnDisable()
        {
            _moveAction?.actionMap?.Disable();
        }

        private void Update()
        {
            int act = ReadAction();
            if (act != ChefSimulation.Action_STAY)
                _pending = act;
        }

        /// <summary>Convert current input state to a single 6-action intent (0 if no input).</summary>
        private int ReadAction()
        {
            // Prefer Input System path when wired up.
            if (_moveAction != null && _interactAction != null)
            {
                if (_interactAction.WasPressedThisFrame())
                    return ChefSimulation.Action_INTERACT;

                Vector2 v = _moveAction.ReadValue<Vector2>();
                return Vec2ToAction(v);
            }

            // Fallback: legacy Input (UnityEngine.Input). This path is the dev-time
            // safety net for cases where the .inputactions asset isn't bound yet.
            if (LocalPlayerIndex == 0)
            {
                if (UnityEngine.Input.GetKeyDown(KeyCode.Space)) return ChefSimulation.Action_INTERACT;
                if (UnityEngine.Input.GetKey(KeyCode.W)) return ChefSimulation.Action_N;
                if (UnityEngine.Input.GetKey(KeyCode.S)) return ChefSimulation.Action_S;
                if (UnityEngine.Input.GetKey(KeyCode.D)) return ChefSimulation.Action_E;
                if (UnityEngine.Input.GetKey(KeyCode.A)) return ChefSimulation.Action_W;
            }
            else
            {
                if (UnityEngine.Input.GetKeyDown(KeyCode.RightShift)) return ChefSimulation.Action_INTERACT;
                if (UnityEngine.Input.GetKey(KeyCode.UpArrow)) return ChefSimulation.Action_N;
                if (UnityEngine.Input.GetKey(KeyCode.DownArrow)) return ChefSimulation.Action_S;
                if (UnityEngine.Input.GetKey(KeyCode.RightArrow)) return ChefSimulation.Action_E;
                if (UnityEngine.Input.GetKey(KeyCode.LeftArrow)) return ChefSimulation.Action_W;
            }
            return ChefSimulation.Action_STAY;
        }

        private static int Vec2ToAction(Vector2 v)
        {
            const float dead = 0.5f;
            float ax = Mathf.Abs(v.x);
            float ay = Mathf.Abs(v.y);
            if (ax < dead && ay < dead) return ChefSimulation.Action_STAY;
            if (ay >= ax)
                return v.y > 0f ? ChefSimulation.Action_N : ChefSimulation.Action_S;
            return v.x > 0f ? ChefSimulation.Action_E : ChefSimulation.Action_W;
        }

        /// <summary>
        /// Called by the 8 Hz tick driver. Returns the latched intent and clears
        /// it so the next tick starts from STAY again.
        /// </summary>
        public int FlushIntent()
        {
            int a = _pending;
            _pending = ChefSimulation.Action_STAY;
            return a;
        }

        /// <summary>Convenience: forward the latched intent directly to the network agent.</summary>
        public void FlushAndSubmitToNetwork()
        {
            if (NetworkAgent == null) return;
            int a = FlushIntent();
            NetworkAgent.SubmitAction(a);
        }
    }
}
